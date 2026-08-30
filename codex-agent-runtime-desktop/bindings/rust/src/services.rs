//! Thin Rust projections of the canonical leaf services.

use crate::async_runtime::{start_operation, start_subscription};
use crate::ffi;
use crate::native_values::{
    OwnedValue, create_owned, decode_connector, decode_conversation_id, decode_form_option,
    decode_form_value, decode_mcp_server, decode_model, decode_plugin_catalog,
    decode_plugin_detail, decode_plugin_install_result, decode_service_tier, decode_skill,
    decode_skill_catalog, decode_skill_chunk, encode_elicitation_response, symbol,
};
use crate::{
    ApprovalDecision, AuthenticationMethod, AuthenticationState, CodexError, CodexOperation,
    CodexStateStream, Connector, ContextInner, Hook, HookCatalog, InstallationScope, Integration,
    IntegrationAuthorizationState, InteractionState, McpServer, McpServerConfiguration, Model,
    OwnedHandle, PendingApproval, PendingElicitation, PluginCatalog, PluginDetail,
    PluginInstallResult, PluginReference, Resolution, ServiceTier, Skill, SkillCatalog, SkillChunk,
    Status, check, copy_string, read_failure,
};
use std::any::Any;
use std::ffi::c_void;
use std::marker::PhantomData;
use std::rc::Rc;
use std::sync::{Arc, Mutex, Weak};

type Release<T> = unsafe extern "C" fn(*mut ffi::Context, *mut *mut T) -> i32;
type StateGet<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut ffi::Snapshot) -> i32;
type StateSubscribe<T> = unsafe extern "C" fn(
    *mut ffi::Context,
    *mut T,
    ffi::StateCallback,
    *mut c_void,
    *mut *mut ffi::Subscription,
) -> i32;
type ServiceOperation<T> = unsafe extern "C" fn(
    *mut ffi::Context,
    *mut T,
    ffi::OperationCallback,
    *mut c_void,
    *mut *mut ffi::Operation,
) -> i32;

macro_rules! ffi_call {
    ($($body:tt)*) => {{
        // SAFETY: every invocation is made through the exact typed public C declaration, with
        // handles, borrowed inputs, callbacks, user data, and output slots validated by its caller.
        unsafe { $($body)* }
    }};
}

#[derive(Clone, Copy)]
pub(crate) struct ExactSymbol<T: Copy> {
    name: &'static [u8],
    function: T,
}

impl<T: Copy> ExactSymbol<T> {
    #[inline]
    pub(crate) fn invoke<R>(self, invocation: impl FnOnce(T) -> R) -> R {
        #[cfg(test)]
        crate::ffi::test_trace_invocation(
            std::str::from_utf8(self.name)
                .expect("C symbol is UTF-8")
                .trim_end_matches('\0'),
        );
        #[cfg(not(test))]
        let _ = self.name;
        invocation(self.function)
    }
}

pub(crate) fn exact_symbol<T: Copy>(
    context: &Arc<ContextInner>,
    name: &'static [u8],
) -> Result<ExactSymbol<T>, CodexError> {
    Ok(ExactSymbol {
        name,
        function: symbol(context, name)?,
    })
}

pub(super) struct ServiceInner<T> {
    pending: Mutex<Vec<RetainedPending>>,
    handle: OwnedHandle<T>,
    _agent: Option<Arc<crate::AgentInner>>,
}

enum RetainedPending {
    Approval {
        identity: Arc<crate::residual_values::BindingIdentity>,
        handle: OwnedHandle<ffi::PendingApproval>,
    },
    Elicitation {
        identity: Arc<crate::residual_values::BindingIdentity>,
        handle: OwnedHandle<ffi::PendingElicitation>,
    },
}

fn release_dynamic<T>(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut T,
    name: &'static [u8],
) -> i32 {
    // SAFETY: each wrapper supplies the exact typed release declaration from codex_agent.h.
    match unsafe { ffi::load_value_symbol::<Release<T>>(api, name) } {
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        Ok(release) => unsafe { release(context, value) },
        Err(_) => ffi::STATUS_INTERNAL_ERROR,
    }
}

unsafe fn release_pending_approval(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut ffi::PendingApproval,
) -> i32 {
    release_dynamic(
        api,
        context,
        value,
        b"codex_agent_pending_approval_destroy\0",
    )
}

unsafe fn release_pending_elicitation(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut ffi::PendingElicitation,
) -> i32 {
    release_dynamic(
        api,
        context,
        value,
        b"codex_agent_pending_elicitation_destroy\0",
    )
}

macro_rules! service_type {
    ($public:ident, $native:ty, $release:ident, $release_symbol:literal, $resource:literal) => {
        // The leaf handles are constructed internally by the later Agent-getter slice; this
        // slice keeps that public dependency deliberately absent while testing the exact handles.
        #[allow(dead_code)]
        unsafe fn $release(
            api: &ffi::Api,
            context: *mut ffi::Context,
            value: *mut *mut $native,
        ) -> i32 {
            release_dynamic(api, context, value, concat!($release_symbol, "\0").as_bytes())
        }

        #[doc = concat!("Thin owned projection of the canonical `", stringify!($public), "` service.")]
        pub struct $public {
            inner: Arc<ServiceInner<$native>>,
            _not_send_or_sync: PhantomData<Rc<()>>,
        }

        impl Clone for $public {
            fn clone(&self) -> Self {
                Self {
                    inner: self.inner.clone(),
                    _not_send_or_sync: PhantomData,
                }
            }
        }

        impl $public {
            #[allow(dead_code)]
            pub(crate) fn from_raw(context: Arc<ContextInner>, raw: *mut $native) -> Self {
                Self {
                    inner: Arc::new(ServiceInner {
                        pending: Mutex::new(Vec::new()),
                        handle: OwnedHandle::new(context, raw, $release, $resource),
                        _agent: None,
                    }),
                    _not_send_or_sync: PhantomData,
                }
            }

            pub(super) fn from_agent(
                context: Arc<ContextInner>,
                raw: *mut $native,
                agent: Arc<crate::AgentInner>,
            ) -> Self {
                Self {
                    inner: Arc::new(ServiceInner {
                        pending: Mutex::new(Vec::new()),
                        handle: OwnedHandle::new(context, raw, $release, $resource),
                        _agent: Some(agent),
                    }),
                    _not_send_or_sync: PhantomData,
                }
            }

            pub(super) fn from_inner(inner: Arc<ServiceInner<$native>>) -> Self {
                Self {
                    inner,
                    _not_send_or_sync: PhantomData,
                }
            }

            pub(super) fn downgrade(&self) -> Weak<ServiceInner<$native>> {
                Arc::downgrade(&self.inner)
            }
        }
    };
}

service_type!(
    CodexAuthentication,
    ffi::Authentication,
    release_authentication,
    "codex_agent_authentication_release",
    "authentication"
);
service_type!(
    CodexConnectors,
    ffi::Connectors,
    release_connectors,
    "codex_agent_connectors_release",
    "connectors"
);
service_type!(
    CodexHooks,
    ffi::Hooks,
    release_hooks,
    "codex_agent_hooks_release",
    "hooks"
);
service_type!(
    CodexIntegrationAuthorization,
    ffi::IntegrationAuthorization,
    release_integration_authorization,
    "codex_agent_integration_authorization_release",
    "integration authorization"
);
service_type!(
    CodexInteractions,
    ffi::Interactions,
    release_interactions,
    "codex_agent_interactions_release",
    "interactions"
);
service_type!(
    CodexMcpServers,
    ffi::McpServers,
    release_mcp_servers,
    "codex_agent_mcp_servers_release",
    "MCP servers"
);
service_type!(
    CodexModels,
    ffi::Models,
    release_models,
    "codex_agent_models_release",
    "models"
);
service_type!(
    CodexPlugins,
    ffi::Plugins,
    release_plugins,
    "codex_agent_plugins_release",
    "plugins"
);
service_type!(
    CodexSkills,
    ffi::Skills,
    release_skills,
    "codex_agent_skills_release",
    "skills"
);

/// Current-value plus subscription projection of one canonical `StateFlow` capability.
pub struct CodexObservableState<T> {
    pub(crate) current: Box<dyn Fn() -> Result<T, CodexError>>,
    pub(crate) subscribe: Box<dyn Fn() -> Result<CodexStateStream<T>, CodexError>>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl<T> CodexObservableState<T> {
    pub(crate) fn from_parts(
        current: impl Fn() -> Result<T, CodexError> + 'static,
        subscribe: impl Fn() -> Result<CodexStateStream<T>, CodexError> + 'static,
    ) -> Self {
        Self {
            current: Box::new(current),
            subscribe: Box::new(subscribe),
            _not_send_or_sync: PhantomData,
        }
    }

    /// Reads the current immutable value through the C ABI getter.
    pub fn current(&self) -> Result<T, CodexError> {
        (self.current)()
    }

    /// Subscribes to the current value and subsequent immutable updates.
    pub fn subscribe(&self) -> Result<CodexStateStream<T>, CodexError> {
        (self.subscribe)()
    }
}

struct Snapshot {
    context: Arc<ContextInner>,
    raw: *mut ffi::Snapshot,
}

impl Drop for Snapshot {
    fn drop(&mut self) {
        self.context.destroy_snapshot(self.raw);
    }
}

fn observable<T, S, P>(
    owner: Arc<ServiceInner<S>>,
    getter_name: &'static [u8],
    subscriber_name: &'static [u8],
    projector: P,
) -> Result<CodexObservableState<T>, CodexError>
where
    T: 'static,
    S: 'static,
    P: Fn(&Arc<ContextInner>, *mut ffi::Snapshot) -> Result<T, CodexError> + Clone + 'static,
{
    let context = owner.handle.context.clone();
    let getter: ExactSymbol<StateGet<S>> = exact_symbol(&context, getter_name)?;
    let subscriber: ExactSymbol<StateSubscribe<S>> = exact_symbol(&context, subscriber_name)?;
    let current_owner = owner.clone();
    let current_projector = projector.clone();
    let current = Box::new(move || {
        let context = current_owner.handle.context.clone();
        let service = current_owner.handle.ptr()?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            getter.invoke(|function| {
                ffi_call! {
                    function(context.ptr(), service, &mut raw)
                }
            }),
            "read service state",
        )?;
        let snapshot = Snapshot { context, raw };
        current_projector(&snapshot.context, snapshot.raw)
    });
    let subscribe = Box::new(move || {
        let service = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        let stream_owner: Arc<dyn Any + Send + Sync> = owner.clone();
        let stream_projector = projector.clone();
        start_subscription(
            context,
            stream_owner,
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            move |callback, user_data, output| {
                subscriber.invoke(|function| {
                    ffi_call! {
                        function(start_context.ptr(), service, callback, user_data, output)
                    }
                })
            },
            move |context, snapshot| stream_projector(context, snapshot),
        )
    });
    Ok(CodexObservableState {
        current,
        subscribe,
        _not_send_or_sync: PhantomData,
    })
}

fn operation<T, S, P>(
    owner: Arc<ServiceInner<S>>,
    _start_name: &'static [u8],
    initiate: impl FnOnce(
        &Arc<ContextInner>,
        *mut S,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32,
    projector: P,
) -> Result<CodexOperation<T>, CodexError>
where
    T: 'static,
    S: 'static,
    P: FnOnce(&Arc<ContextInner>, *mut ffi::Operation) -> Result<T, CodexError> + 'static,
{
    let service = owner.handle.ptr()?;
    let context = owner.handle.context.clone();
    let start_context = context.clone();
    let operation_owner: Arc<dyn Any + Send + Sync> = owner;
    start_operation(
        context,
        operation_owner,
        move |callback, user_data, output| {
            initiate(&start_context, service, callback, user_data, output)
        },
        projector,
    )
}

fn no_arg_operation<S: 'static>(
    owner: Arc<ServiceInner<S>>,
    name: &'static [u8],
) -> Result<CodexOperation<()>, CodexError> {
    let function: ExactSymbol<ServiceOperation<S>> = exact_symbol(&owner.handle.context, name)?;
    operation(
        owner,
        name,
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |context, service, callback, user_data, output| {
            function.invoke(|call| {
                ffi_call! {
                    call(context.ptr(), service, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    )
}

fn available<S>(owner: &Arc<ServiceInner<S>>, name: &'static [u8]) -> Result<bool, CodexError> {
    type Available<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32) -> i32;
    let context = &owner.handle.context;
    let function: ExactSymbol<Available<S>> = exact_symbol(context, name)?;
    let service = owner.handle.ptr()?;
    let mut result = -1;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        function.invoke(|call| {
            ffi_call! {
                call(context.ptr(), service, &mut result)
            }
        }),
        "read service availability",
    )?;
    match result {
        0 => Ok(false),
        1 => Ok(true),
        _ => Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned a non-Boolean availability",
        )),
    }
}

fn operation_value<T, V>(
    context: &Arc<ContextInner>,
    operation: *mut ffi::Operation,
    getter_name: &'static [u8],
    decoder: impl FnOnce(&Arc<ContextInner>, *mut V) -> Result<T, CodexError>,
) -> Result<T, CodexError> {
    type Getter<V> =
        unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Operation, *mut *mut V) -> i32;
    let getter: ExactSymbol<Getter<V>> = exact_symbol(context, getter_name)?;
    let mut raw = std::ptr::null_mut();
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        getter.invoke(|call| {
            ffi_call! {
                call(context.ptr(), operation, &mut raw)
            }
        }),
        "read service operation value",
    )?;
    decoder(context, raw)
}

fn operation_values<T, V>(
    context: &Arc<ContextInner>,
    operation: *mut ffi::Operation,
    count_name: &'static [u8],
    at_name: &'static [u8],
    decoder: impl Fn(&Arc<ContextInner>, *mut V) -> Result<T, CodexError>,
) -> Result<Vec<T>, CodexError> {
    type Count = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Operation, *mut usize) -> i32;
    type At<V> =
        unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Operation, usize, *mut *mut V) -> i32;
    let count: ExactSymbol<Count> = exact_symbol(context, count_name)?;
    let at: ExactSymbol<At<V>> = exact_symbol(context, at_name)?;
    let mut length = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        count.invoke(|call| {
            ffi_call! {
                call(context.ptr(), operation, &mut length)
            }
        }),
        "read service operation count",
    )?;
    let mut result = Vec::with_capacity(length);
    for index in 0..length {
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            at.invoke(|call| {
                ffi_call! {
                    call(context.ptr(), operation, index, &mut raw)
                }
            }),
            "read service operation item",
        )?;
        result.push(decoder(context, raw)?);
    }
    Ok(result)
}

fn boolean_state(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
) -> Result<bool, CodexError> {
    type Value = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, *mut i32) -> i32;
    let value: ExactSymbol<Value> = exact_symbol(context, b"codex_agent_state_boolean_value\0")?;
    let mut result = -1;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        value.invoke(|call| {
            ffi_call! {
                call(context.ptr(), snapshot, &mut result)
            }
        }),
        "read Boolean service state",
    )?;
    match result {
        0 => Ok(false),
        1 => Ok(true),
        _ => Err(CodexError::new(
            Status::InternalError,
            "native state is not Boolean",
        )),
    }
}

impl CodexAuthentication {
    /// Authentication state current value and updates.
    pub fn state(&self) -> Result<CodexObservableState<AuthenticationState>, CodexError> {
        observable(
            self.inner.clone(),
            b"codex_agent_authentication_state_get\0",
            b"codex_agent_authentication_state_subscribe\0",
            decode_authentication_snapshot,
        )
    }

    /// Whether credentials currently authenticate requests, as current value plus updates.
    pub fn is_authenticated(&self) -> Result<CodexObservableState<bool>, CodexError> {
        observable(
            self.inner.clone(),
            b"codex_agent_authentication_is_authenticated_get\0",
            b"codex_agent_authentication_is_authenticated_subscribe\0",
            boolean_state,
        )
    }

    /// Whether an authentication attempt is running, as current value plus updates.
    pub fn is_authenticating(&self) -> Result<CodexObservableState<bool>, CodexError> {
        observable(
            self.inner.clone(),
            b"codex_agent_authentication_is_authenticating_get\0",
            b"codex_agent_authentication_is_authenticating_subscribe\0",
            boolean_state,
        )
    }

    /// Starts authentication with the requested canonical method.
    pub fn authenticate(
        &self,
        method: &AuthenticationMethod,
    ) -> Result<CodexOperation<()>, CodexError> {
        authenticate(self.inner.clone(), method)
    }

    /// Cancels the current authentication attempt.
    pub fn cancel(&self) -> Result<CodexOperation<()>, CodexError> {
        no_arg_operation(self.inner.clone(), b"codex_agent_authentication_cancel\0")
    }

    /// Signs out of the local Codex session.
    pub fn sign_out(&self) -> Result<CodexOperation<()>, CodexError> {
        no_arg_operation(self.inner.clone(), b"codex_agent_authentication_sign_out\0")
    }
}

impl CodexConnectors {
    /// Whether connector support is available in the prepared runtime.
    pub fn is_available(&self) -> Result<bool, CodexError> {
        available(&self.inner, b"codex_agent_connectors_is_available\0")
    }

    /// Lists connectors, preserving native ordering and duplicates.
    pub fn list(&self, force_reload: bool) -> Result<CodexOperation<Vec<Connector>>, CodexError> {
        type List = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Connectors,
            i32,
            ffi::OperationCallback,
            *mut c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let function: ExactSymbol<List> =
            exact_symbol(&self.inner.handle.context, b"codex_agent_connectors_list\0")?;
        operation(
            self.inner.clone(),
            b"codex_agent_connectors_list\0",
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            move |context, service, callback, user_data, output| {
                function.invoke(|call| {
                    ffi_call! {
                        call(
                            context.ptr(),
                            service,
                            i32::from(force_reload),
                            callback,
                            user_data,
                            output,
                        )
                    }
                })
            },
            |context, operation| {
                operation_values(
                    context,
                    operation,
                    b"codex_agent_operation_connectors_count\0",
                    b"codex_agent_operation_connector_at\0",
                    decode_connector,
                )
            },
        )
    }
}

impl CodexIntegrationAuthorization {
    /// Authorization state current value and updates.
    pub fn state(&self) -> Result<CodexObservableState<IntegrationAuthorizationState>, CodexError> {
        observable(
            self.inner.clone(),
            b"codex_agent_integration_authorization_state_get\0",
            b"codex_agent_integration_authorization_state_subscribe\0",
            decode_integration_authorization_snapshot,
        )
    }

    /// Active integration current value and updates, preserving absence.
    pub fn active(&self) -> Result<CodexObservableState<Option<Integration>>, CodexError> {
        observable(
            self.inner.clone(),
            b"codex_agent_integration_authorization_active_get\0",
            b"codex_agent_integration_authorization_active_subscribe\0",
            decode_active_integration_snapshot,
        )
    }

    /// Whether authorization is running, as current value plus updates.
    pub fn is_authorizing(&self) -> Result<CodexObservableState<bool>, CodexError> {
        observable(
            self.inner.clone(),
            b"codex_agent_integration_authorization_is_authorizing_get\0",
            b"codex_agent_integration_authorization_is_authorizing_subscribe\0",
            boolean_state,
        )
    }

    /// Starts authorization for a connector or MCP-server integration.
    pub fn authorize(&self, target: &Integration) -> Result<CodexOperation<()>, CodexError> {
        authorize_integration(self.inner.clone(), target)
    }

    /// Cancels the active integration authorization.
    pub fn cancel(&self) -> Result<CodexOperation<()>, CodexError> {
        no_arg_operation(
            self.inner.clone(),
            b"codex_agent_integration_authorization_cancel\0",
        )
    }
}

impl CodexHooks {
    /// Whether hook support is available in the prepared runtime.
    pub fn is_available(&self) -> Result<bool, CodexError> {
        available(&self.inner, b"codex_agent_hooks_is_available\0")
    }

    /// Lists the immutable hook catalog.
    pub fn list(&self) -> Result<CodexOperation<HookCatalog>, CodexError> {
        let function: ExactSymbol<ServiceOperation<ffi::Hooks>> =
            exact_symbol(&self.inner.handle.context, b"codex_agent_hooks_list\0")?;
        operation(
            self.inner.clone(),
            b"codex_agent_hooks_list\0",
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            move |context, service, callback, user_data, output| {
                function.invoke(|call| {
                    ffi_call! {
                        call(context.ptr(), service, callback, user_data, output)
                    }
                })
            },
            |context, operation| {
                operation_value(
                    context,
                    operation,
                    b"codex_agent_operation_hook_catalog\0",
                    decode_hook_catalog,
                )
            },
        )
    }

    /// Installs a hook directory in the requested scope.
    pub fn install(
        &self,
        directory: impl Into<String>,
        scope: InstallationScope,
    ) -> Result<CodexOperation<Hook>, CodexError> {
        install_hook(self.inner.clone(), directory.into(), scope)
    }

    /// Removes the exact hook value through the canonical operation.
    pub fn uninstall(&self, hook: &Hook) -> Result<CodexOperation<()>, CodexError> {
        hook_operation(self.inner.clone(), hook, b"codex_agent_hooks_uninstall\0")
    }

    /// Trusts the exact hook value through the canonical operation.
    pub fn trust(&self, hook: &Hook) -> Result<CodexOperation<()>, CodexError> {
        hook_operation(self.inner.clone(), hook, b"codex_agent_hooks_trust\0")
    }
}

impl CodexMcpServers {
    /// Whether MCP-server support is available in the prepared runtime.
    pub fn is_available(&self) -> Result<bool, CodexError> {
        available(&self.inner, b"codex_agent_mcp_servers_is_available\0")
    }

    /// Lists MCP servers, preserving native ordering and identity values.
    pub fn list(&self) -> Result<CodexOperation<Vec<McpServer>>, CodexError> {
        let function: ExactSymbol<ServiceOperation<ffi::McpServers>> = exact_symbol(
            &self.inner.handle.context,
            b"codex_agent_mcp_servers_list\0",
        )?;
        operation(
            self.inner.clone(),
            b"codex_agent_mcp_servers_list\0",
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            move |context, service, callback, user_data, output| {
                function.invoke(|call| {
                    ffi_call! {
                        call(context.ptr(), service, callback, user_data, output)
                    }
                })
            },
            |context, operation| {
                operation_values(
                    context,
                    operation,
                    b"codex_agent_operation_mcp_servers_count\0",
                    b"codex_agent_operation_mcp_server_at\0",
                    decode_mcp_server,
                )
            },
        )
    }

    /// Adds one MCP server configuration.
    pub fn add(
        &self,
        configuration: &McpServerConfiguration,
    ) -> Result<CodexOperation<McpServer>, CodexError> {
        mcp_add(self.inner.clone(), configuration)
    }

    /// Removes one MCP server.
    pub fn remove(&self, server: &McpServer) -> Result<CodexOperation<()>, CodexError> {
        mcp_remove(self.inner.clone(), server)
    }
}

impl CodexInteractions {
    /// Ordered interaction state current value and updates.
    pub fn state(&self) -> Result<CodexObservableState<InteractionState>, CodexError> {
        let owner = self.inner.clone();
        observable(
            self.inner.clone(),
            b"codex_agent_interactions_state_get\0",
            b"codex_agent_interactions_state_subscribe\0",
            move |context, snapshot| decode_interaction_state_snapshot(context, snapshot, &owner),
        )
    }

    /// Pending approvals current value and updates, preserving order and native identity.
    pub fn approvals(&self) -> Result<CodexObservableState<Vec<PendingApproval>>, CodexError> {
        let owner = self.inner.clone();
        observable(
            self.inner.clone(),
            b"codex_agent_interactions_approvals_get\0",
            b"codex_agent_interactions_approvals_subscribe\0",
            move |context, snapshot| decode_approvals_snapshot(context, snapshot, &owner),
        )
    }

    /// Pending elicitations current value and updates, preserving order and native identity.
    pub fn elicitations(
        &self,
    ) -> Result<CodexObservableState<Vec<PendingElicitation>>, CodexError> {
        let owner = self.inner.clone();
        observable(
            self.inner.clone(),
            b"codex_agent_interactions_elicitations_get\0",
            b"codex_agent_interactions_elicitations_subscribe\0",
            move |context, snapshot| decode_elicitations_snapshot(context, snapshot, &owner),
        )
    }

    /// Resolves the exact approval identity emitted by this service.
    pub fn resolve_approval(
        &self,
        approval: &PendingApproval,
        decision: ApprovalDecision,
    ) -> Result<CodexOperation<()>, CodexError> {
        interaction_approval_operation(self.inner.clone(), approval, decision)
    }

    /// Resolves the exact elicitation identity emitted by this service.
    pub fn resolve_elicitation(
        &self,
        elicitation: &PendingElicitation,
        response: &crate::ElicitationResponse,
    ) -> Result<CodexOperation<()>, CodexError> {
        interaction_elicitation_operation(self.inner.clone(), elicitation, response)
    }

    /// Opens the exact elicitation identity in the configured local browser policy.
    pub fn open_url(
        &self,
        elicitation: &PendingElicitation,
    ) -> Result<CodexOperation<()>, CodexError> {
        interaction_open_url(self.inner.clone(), elicitation)
    }
}

impl CodexModels {
    /// Lists models, preserving native ordering and duplicates.
    pub fn list(&self) -> Result<CodexOperation<Vec<Model>>, CodexError> {
        let function: ExactSymbol<ServiceOperation<ffi::Models>> =
            exact_symbol(&self.inner.handle.context, b"codex_agent_models_list\0")?;
        operation(
            self.inner.clone(),
            b"codex_agent_models_list\0",
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            move |context, service, callback, user_data, output| {
                function.invoke(|call| {
                    ffi_call! {
                        call(context.ptr(), service, callback, user_data, output)
                    }
                })
            },
            |context, operation| {
                operation_values(
                    context,
                    operation,
                    b"codex_agent_operation_models_count\0",
                    b"codex_agent_operation_model_at\0",
                    decode_model,
                )
            },
        )
    }

    /// Resolves a model according to the canonical policy.
    pub fn resolve(&self, resolution: Resolution) -> Result<CodexOperation<Model>, CodexError> {
        type Resolve = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Models,
            i32,
            ffi::OperationCallback,
            *mut c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let function: ExactSymbol<Resolve> =
            exact_symbol(&self.inner.handle.context, b"codex_agent_models_resolve\0")?;
        operation(
            self.inner.clone(),
            b"codex_agent_models_resolve\0",
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            move |context, service, callback, user_data, output| {
                function.invoke(|call| {
                    ffi_call! {
                        call(
                            context.ptr(),
                            service,
                            resolution as i32,
                            callback,
                            user_data,
                            output,
                        )
                    }
                })
            },
            |context, operation| {
                operation_value(
                    context,
                    operation,
                    b"codex_agent_operation_model\0",
                    decode_model,
                )
            },
        )
    }

    /// Resolves effort for a concrete model.
    pub fn resolve_effort(
        &self,
        model: &Model,
        resolution: Resolution,
    ) -> Result<CodexOperation<String>, CodexError> {
        model_effort(self.inner.clone(), model, resolution)
    }

    /// Resolves an optional service tier for a concrete model.
    pub fn resolve_service_tier(
        &self,
        model: &Model,
        resolution: Resolution,
    ) -> Result<CodexOperation<Option<ServiceTier>>, CodexError> {
        model_service_tier(self.inner.clone(), model, resolution)
    }
}

impl CodexPlugins {
    /// Whether plugin support is available in the prepared runtime.
    pub fn is_available(&self) -> Result<bool, CodexError> {
        available(&self.inner, b"codex_agent_plugins_is_available\0")
    }

    /// Lists the immutable plugin catalog.
    pub fn list(&self, force_reload: bool) -> Result<CodexOperation<PluginCatalog>, CodexError> {
        plugin_list(self.inner.clone(), force_reload)
    }

    /// Reads plugin detail.
    pub fn read(
        &self,
        plugin: &PluginReference,
    ) -> Result<CodexOperation<PluginDetail>, CodexError> {
        plugin_operation(
            self.inner.clone(),
            plugin,
            b"codex_agent_plugins_read\0",
            b"codex_agent_operation_plugin_detail\0",
            decode_plugin_detail,
        )
    }

    /// Installs a plugin and returns its immutable result.
    pub fn install(
        &self,
        plugin: &PluginReference,
    ) -> Result<CodexOperation<PluginInstallResult>, CodexError> {
        plugin_operation(
            self.inner.clone(),
            plugin,
            b"codex_agent_plugins_install\0",
            b"codex_agent_operation_plugin_install_result\0",
            decode_plugin_install_result,
        )
    }

    /// Uninstalls a plugin.
    pub fn uninstall(&self, plugin: &PluginReference) -> Result<CodexOperation<()>, CodexError> {
        plugin_unit(self.inner.clone(), plugin)
    }
}

impl CodexSkills {
    /// Whether skill support is available in the prepared runtime.
    pub fn is_available(&self) -> Result<bool, CodexError> {
        available(&self.inner, b"codex_agent_skills_is_available\0")
    }

    /// Lists the immutable skill catalog.
    pub fn list(&self, force_reload: bool) -> Result<CodexOperation<SkillCatalog>, CodexError> {
        skill_list(self.inner.clone(), force_reload)
    }

    /// Reads a skill content chunk from a byte offset.
    pub fn read(
        &self,
        path: impl Into<String>,
        offset: i64,
    ) -> Result<CodexOperation<SkillChunk>, CodexError> {
        skill_read(self.inner.clone(), path.into(), offset)
    }

    /// Installs a skill directory.
    pub fn install(
        &self,
        directory: impl Into<String>,
        scope: InstallationScope,
    ) -> Result<CodexOperation<Skill>, CodexError> {
        skill_install(self.inner.clone(), directory.into(), scope)
    }

    /// Uninstalls a skill.
    pub fn uninstall(&self, skill: &Skill) -> Result<CodexOperation<()>, CodexError> {
        skill_uninstall(self.inner.clone(), skill)
    }
}

// The less repetitive native value encoders/decoders and the three stateful services follow below.
// They intentionally resolve stable public C symbols directly; there is no local runtime behavior.

fn scalar_i32<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    name: &'static [u8],
) -> Result<i32, CodexError> {
    type Getter<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32) -> i32;
    let getter: ExactSymbol<Getter<T>> = exact_symbol(context, name)?;
    let mut value = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        getter.invoke(|call| {
            ffi_call! {
                call(context.ptr(), raw, &mut value)
            }
        }),
        "read native service scalar",
    )?;
    Ok(value)
}

fn native_string<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    name: &'static [u8],
) -> Result<String, CodexError> {
    type Getter<T> =
        unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut u8, usize, *mut usize) -> i32;
    let getter: ExactSymbol<Getter<T>> = exact_symbol(context, name)?;
    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
    copy_string(|buffer, capacity, required| {
        getter.invoke(|call| {
            ffi_call! {
                call(context.ptr(), raw, buffer, capacity, required)
            }
        })
    })
}

fn child<T, U>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    name: &'static [u8],
) -> Result<*mut U, CodexError> {
    type Getter<T, U> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut U) -> i32;
    let getter: ExactSymbol<Getter<T, U>> = exact_symbol(context, name)?;
    let mut value = std::ptr::null_mut();
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        getter.invoke(|call| {
            ffi_call! {
                call(context.ptr(), raw, &mut value)
            }
        }),
        "read native service child",
    )?;
    if value.is_null() {
        Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned an absent service child",
        ))
    } else {
        Ok(value)
    }
}

fn decode_authorization_url(
    context: &Arc<ContextInner>,
    raw: *mut ffi::AuthorizationUrl,
) -> Result<crate::AuthorizationUrl, CodexError> {
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_authorization_url_destroy\0",
        "authorization URL",
    )?;
    let result = crate::AuthorizationUrl {
        value: native_string(
            context,
            owned.raw(),
            b"codex_agent_authorization_url_value_copy\0",
        )?,
        purpose: crate::AuthorizationPurpose::from_raw(scalar_i32(
            context,
            owned.raw(),
            b"codex_agent_authorization_url_purpose\0",
        )?)
        .ok_or_else(|| CodexError::new(Status::InternalError, "unknown authorization purpose"))?,
    };
    owned.close()?;
    Ok(result)
}

fn decode_authentication_snapshot(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
) -> Result<AuthenticationState, CodexError> {
    let raw = child::<ffi::Snapshot, ffi::AuthenticationState>(
        context,
        snapshot,
        b"codex_agent_authentication_state_value\0",
    )?;
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_authentication_state_destroy\0",
        "authentication state",
    )?;
    let status = crate::AuthenticationStatus::from_raw(scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_authentication_state_status\0",
    )?)
    .ok_or_else(|| CodexError::new(Status::InternalError, "unknown authentication status"))?;
    let optional_url = |has_name,
                        value_name|
     -> Result<Option<crate::AuthorizationUrl>, CodexError> {
        if scalar_i32(context, owned.raw(), has_name)? == 0 {
            Ok(None)
        } else {
            decode_authorization_url(context, child(context, owned.raw(), value_name)?).map(Some)
        }
    };
    let pending_sign_in_url = optional_url(
        b"codex_agent_authentication_state_has_pending_sign_in_url\0",
        b"codex_agent_authentication_state_pending_sign_in_url\0",
    )?;
    let device_verification_url = optional_url(
        b"codex_agent_authentication_state_has_device_verification_url\0",
        b"codex_agent_authentication_state_device_verification_url\0",
    )?;
    let device_user_code = if scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_authentication_state_has_device_user_code\0",
    )? == 0
    {
        None
    } else {
        Some(native_string(
            context,
            owned.raw(),
            b"codex_agent_authentication_state_device_user_code_copy\0",
        )?)
    };
    let failure = if scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_authentication_state_has_failure\0",
    )? == 0
    {
        None
    } else {
        Some(read_failure(
            context,
            child(
                context,
                owned.raw(),
                b"codex_agent_authentication_state_failure\0",
            )?,
        )?)
    };
    owned.close()?;
    Ok(AuthenticationState::new(
        status,
        pending_sign_in_url,
        device_verification_url,
        device_user_code,
        failure,
    ))
}

fn authenticate(
    owner: Arc<ServiceInner<ffi::Authentication>>,
    method: &AuthenticationMethod,
) -> Result<CodexOperation<()>, CodexError> {
    type ApiKeyCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *mut *mut ffi::AuthenticationMethodApiKey,
    ) -> i32;
    type ApiKeyAuthenticate = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Authentication,
        *mut ffi::AuthenticationMethodApiKey,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    type BrowserCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut *mut ffi::AuthenticationMethodChatGptBrowser,
    ) -> i32;
    type BrowserAuthenticate = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Authentication,
        *mut ffi::AuthenticationMethodChatGptBrowser,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    type DeviceCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut *mut ffi::AuthenticationMethodChatGptDeviceCode,
    ) -> i32;
    type DeviceAuthenticate = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Authentication,
        *mut ffi::AuthenticationMethodChatGptDeviceCode,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;

    let context = owner.handle.context.clone();
    match method {
        AuthenticationMethod::ApiKey(api_key) => {
            let create: ApiKeyCreate = symbol(
                &context,
                b"codex_agent_authentication_method_api_key_create\0",
            )?;
            let value = ffi::StringView::new(&api_key.value);
            let native = create_owned(
                &context,
                b"codex_agent_authentication_method_api_key_destroy\0",
                "API-key authentication method",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { create(context.ptr(), &value, out) },
            )?;
            let function: ExactSymbol<ApiKeyAuthenticate> = exact_symbol(
                &context,
                b"codex_agent_authentication_authenticate_api_key\0",
            )?;
            let raw = native.raw();
            let result = operation(
                owner,
                b"codex_agent_authentication_authenticate_api_key\0",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                move |current, service, callback, user_data, output| {
                    function.invoke(|call| {
                        ffi_call! {
                            call(current.ptr(), service, raw, callback, user_data, output)
                        }
                    })
                },
                |_, _| Ok(()),
            );
            native.close()?;
            result
        }
        AuthenticationMethod::ChatGptBrowser(_) => {
            let create: BrowserCreate = symbol(
                &context,
                b"codex_agent_authentication_method_chat_gpt_browser_create\0",
            )?;
            let native = create_owned(
                &context,
                b"codex_agent_authentication_method_chat_gpt_browser_destroy\0",
                "browser authentication method",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { create(context.ptr(), out) },
            )?;
            let function: ExactSymbol<BrowserAuthenticate> = exact_symbol(
                &context,
                b"codex_agent_authentication_authenticate_chat_gpt_browser\0",
            )?;
            let raw = native.raw();
            let result = operation(
                owner,
                b"codex_agent_authentication_authenticate_chat_gpt_browser\0",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                move |current, service, callback, user_data, output| {
                    function.invoke(|call| {
                        ffi_call! {
                            call(current.ptr(), service, raw, callback, user_data, output)
                        }
                    })
                },
                |_, _| Ok(()),
            );
            native.close()?;
            result
        }
        AuthenticationMethod::ChatGptDeviceCode(_) => {
            let create: DeviceCreate = symbol(
                &context,
                b"codex_agent_authentication_method_chat_gpt_device_code_create\0",
            )?;
            let native = create_owned(
                &context,
                b"codex_agent_authentication_method_chat_gpt_device_code_destroy\0",
                "device-code authentication method",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { create(context.ptr(), out) },
            )?;
            let function: ExactSymbol<DeviceAuthenticate> = exact_symbol(
                &context,
                b"codex_agent_authentication_authenticate_chat_gpt_device_code\0",
            )?;
            let raw = native.raw();
            let result = operation(
                owner,
                b"codex_agent_authentication_authenticate_chat_gpt_device_code\0",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                move |current, service, callback, user_data, output| {
                    function.invoke(|call| {
                        ffi_call! {
                            call(current.ptr(), service, raw, callback, user_data, output)
                        }
                    })
                },
                |_, _| Ok(()),
            );
            native.close()?;
            result
        }
    }
}

fn decode_hook_catalog(
    context: &Arc<ContextInner>,
    raw: *mut ffi::HookCatalog,
) -> Result<HookCatalog, CodexError> {
    type Count = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::HookCatalog, *mut usize) -> i32;
    type At = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::HookCatalog,
        usize,
        *mut *mut ffi::Hook,
    ) -> i32;
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_hook_catalog_destroy\0",
        "hook catalog",
    )?;
    let count: Count = symbol(context, b"codex_agent_hook_catalog_hooks_count\0")?;
    let at: At = symbol(context, b"codex_agent_hook_catalog_hooks_at\0")?;
    let mut length = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { count(context.ptr(), owned.raw(), &mut length) },
        "read hook catalog count",
    )?;
    let mut hooks = Vec::with_capacity(length);
    for index in 0..length {
        let mut hook = std::ptr::null_mut();
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { at(context.ptr(), owned.raw(), index, &mut hook) },
            "read hook catalog item",
        )?;
        hooks.push(decode_hook(context, hook)?);
    }
    let strings = |count_name, copy_name| -> Result<Vec<String>, CodexError> {
        type CopyAt = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::HookCatalog,
            usize,
            *mut u8,
            usize,
            *mut usize,
        ) -> i32;
        let count: Count = symbol(context, count_name)?;
        let copy: CopyAt = symbol(context, copy_name)?;
        let mut length = 0;
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { count(context.ptr(), owned.raw(), &mut length) },
            "read hook catalog string count",
        )?;
        (0..length)
            .map(|index| {
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                copy_string(|buffer, capacity, required| unsafe {
                    copy(
                        context.ptr(),
                        owned.raw(),
                        index,
                        buffer,
                        capacity,
                        required,
                    )
                })
            })
            .collect()
    };
    let warnings = strings(
        b"codex_agent_hook_catalog_warnings_count\0",
        b"codex_agent_hook_catalog_warnings_copy_at\0",
    )?;
    let errors = strings(
        b"codex_agent_hook_catalog_errors_count\0",
        b"codex_agent_hook_catalog_errors_copy_at\0",
    )?;
    owned.close()?;
    Ok(HookCatalog::new(hooks, warnings, errors))
}

fn decode_hook(context: &Arc<ContextInner>, raw: *mut ffi::Hook) -> Result<Hook, CodexError> {
    let owned = OwnedValue::new(context, raw, b"codex_agent_hook_destroy\0", "hook")?;
    let handler = decode_hook_handler(
        context,
        child(context, owned.raw(), b"codex_agent_hook_handler\0")?,
    )?;
    let optional = |has, copy| -> Result<Option<String>, CodexError> {
        (scalar_i32(context, owned.raw(), has)? != 0)
            .then(|| native_string(context, owned.raw(), copy))
            .transpose()
    };
    let value = Hook::new(
        native_string(context, owned.raw(), b"codex_agent_hook_key_copy\0")?,
        native_string(
            context,
            owned.raw(),
            b"codex_agent_hook_current_hash_copy\0",
        )?,
        scalar_i32(context, owned.raw(), b"codex_agent_hook_is_enabled\0")? != 0,
        native_string(context, owned.raw(), b"codex_agent_hook_event_name_copy\0")?,
        handler,
        scalar_i32(context, owned.raw(), b"codex_agent_hook_is_managed\0")? != 0,
        native_string(context, owned.raw(), b"codex_agent_hook_source_copy\0")?,
        native_string(context, owned.raw(), b"codex_agent_hook_source_path_copy\0")?,
        scalar_i64(context, owned.raw(), b"codex_agent_hook_timeout_seconds\0")?,
        crate::HookTrustStatus::from_raw(scalar_i32(
            context,
            owned.raw(),
            b"codex_agent_hook_trust_status\0",
        )?)
        .ok_or_else(|| CodexError::new(Status::InternalError, "unknown hook trust status"))?,
        optional(
            b"codex_agent_hook_has_matcher\0",
            b"codex_agent_hook_matcher_copy\0",
        )?,
        optional(
            b"codex_agent_hook_has_plugin_id\0",
            b"codex_agent_hook_plugin_id_copy\0",
        )?,
        optional(
            b"codex_agent_hook_has_status_message\0",
            b"codex_agent_hook_status_message_copy\0",
        )?,
        crate::ResourceOrigin::from_raw(scalar_i32(
            context,
            owned.raw(),
            b"codex_agent_hook_origin\0",
        )?),
        scalar_i32(context, owned.raw(), b"codex_agent_hook_can_uninstall\0")? != 0,
    );
    owned.close()?;
    Ok(value)
}

fn scalar_i64<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    name: &'static [u8],
) -> Result<i64, CodexError> {
    type Getter<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i64) -> i32;
    let getter: Getter<T> = symbol(context, name)?;
    let mut value = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { getter(context.ptr(), raw, &mut value) },
        "read native i64",
    )?;
    Ok(value)
}

fn decode_hook_handler(
    context: &Arc<ContextInner>,
    raw: *mut ffi::HookHandler,
) -> Result<crate::HookHandler, CodexError> {
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_hook_handler_destroy\0",
        "hook handler",
    )?;
    let result = match scalar_i32(context, owned.raw(), b"codex_agent_hook_handler_kind\0")? {
        0 => crate::HookHandler::Agent(crate::AgentHookHandler::INSTANCE),
        1 => {
            let command: *mut ffi::HookHandlerCommand =
                child(context, owned.raw(), b"codex_agent_hook_handler_command\0")?;
            let command = OwnedValue::new(
                context,
                command,
                b"codex_agent_hook_handler_command_destroy\0",
                "command hook handler",
            )?;
            let value = crate::CommandHookHandler::new(
                native_string(
                    context,
                    command.raw(),
                    b"codex_agent_hook_handler_command_command_copy\0",
                )?,
                scalar_i32(
                    context,
                    command.raw(),
                    b"codex_agent_hook_handler_command_is_async\0",
                )? != 0,
            );
            command.close()?;
            crate::HookHandler::Command(value)
        }
        2 => {
            let tool: *mut ffi::HookHandlerMcpTool =
                child(context, owned.raw(), b"codex_agent_hook_handler_mcp_tool\0")?;
            let tool = OwnedValue::new(
                context,
                tool,
                b"codex_agent_hook_handler_mcp_tool_destroy\0",
                "MCP hook handler",
            )?;
            let value = crate::McpToolHookHandler::new(
                native_string(
                    context,
                    tool.raw(),
                    b"codex_agent_hook_handler_mcp_tool_server_copy\0",
                )?,
                native_string(
                    context,
                    tool.raw(),
                    b"codex_agent_hook_handler_mcp_tool_tool_copy\0",
                )?,
            );
            tool.close()?;
            crate::HookHandler::McpTool(value)
        }
        3 => crate::HookHandler::Prompt(crate::PromptHookHandler::INSTANCE),
        _ => {
            return Err(CodexError::new(
                Status::InternalError,
                "unknown hook handler kind",
            ));
        }
    };
    owned.close()?;
    Ok(result)
}

fn string_views(values: &[String]) -> Vec<ffi::StringView> {
    values
        .iter()
        .map(|value| ffi::StringView::new(value))
        .collect()
}

fn optional_view(value: &Option<String>) -> ffi::StringView {
    value
        .as_deref()
        .map_or_else(ffi::StringView::absent, ffi::StringView::new)
}

fn create_service_tier<'a>(
    context: &'a Arc<ContextInner>,
    value: &ServiceTier,
) -> Result<OwnedValue<'a, ffi::ServiceTier>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        *mut *mut ffi::ServiceTier,
    ) -> i32;
    let create: Create = symbol(context, b"codex_agent_service_tier_create\0")?;
    let id = ffi::StringView::new(&value.id);
    let name = ffi::StringView::new(&value.name);
    let description = ffi::StringView::new(&value.description);
    create_owned(
        context,
        b"codex_agent_service_tier_destroy\0",
        "service tier input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe { create(context.ptr(), &id, &name, &description, out) },
    )
}

fn create_model<'a>(
    context: &'a Arc<ContextInner>,
    value: &Model,
) -> Result<OwnedValue<'a, ffi::Model>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        usize,
        *const ffi::StringView,
        i32,
        *const *mut ffi::ServiceTier,
        usize,
        i32,
        *const ffi::StringView,
        *mut *mut ffi::Model,
    ) -> i32;
    let tiers: Vec<_> = value
        .service_tiers
        .iter()
        .map(|tier| create_service_tier(context, tier))
        .collect::<Result<_, _>>()?;
    let tier_handles: Vec<_> = tiers.iter().map(OwnedValue::raw).collect();
    let efforts = string_views(&value.supported_efforts);
    let id = ffi::StringView::new(&value.id);
    let display_name = ffi::StringView::new(&value.display_name);
    let description = ffi::StringView::new(&value.description);
    let default_effort = ffi::StringView::new(&value.default_effort);
    let default_service_tier = optional_view(&value.default_service_tier);
    let create: Create = symbol(context, b"codex_agent_model_create\0")?;
    create_owned(
        context,
        b"codex_agent_model_destroy\0",
        "model input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &id,
                &display_name,
                &description,
                efforts.as_ptr(),
                efforts.len(),
                &default_effort,
                i32::from(value.is_default),
                tier_handles.as_ptr(),
                tier_handles.len(),
                i32::from(value.default_service_tier.is_some()),
                &default_service_tier,
                out,
            )
        },
    )
}

fn create_plugin_reference<'a>(
    context: &'a Arc<ContextInner>,
    value: &PluginReference,
) -> Result<OwnedValue<'a, ffi::PluginReference>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        *mut *mut ffi::PluginReference,
    ) -> i32;
    let id = ffi::StringView::new(&value.id);
    let name = ffi::StringView::new(&value.name);
    let marketplace = ffi::StringView::new(&value.marketplace_name);
    let path = optional_view(&value.marketplace_path);
    let remote = optional_view(&value.remote_plugin_id);
    let create: Create = symbol(context, b"codex_agent_plugin_reference_create\0")?;
    create_owned(
        context,
        b"codex_agent_plugin_reference_destroy\0",
        "plugin reference input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &id,
                &name,
                &marketplace,
                i32::from(value.marketplace_path.is_some()),
                &path,
                i32::from(value.remote_plugin_id.is_some()),
                &remote,
                out,
            )
        },
    )
}

fn create_skill<'a>(
    context: &'a Arc<ContextInner>,
    value: &Skill,
) -> Result<OwnedValue<'a, ffi::Skill>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        i32,
        i32,
        i32,
        *const ffi::StringView,
        *const ffi::StringView,
        usize,
        i32,
        i32,
        i32,
        *mut *mut ffi::Skill,
    ) -> i32;
    let name = ffi::StringView::new(&value.name);
    let display_name = ffi::StringView::new(&value.display_name);
    let description = ffi::StringView::new(&value.description);
    let path = ffi::StringView::new(&value.path);
    let brand = optional_view(&value.brand_color);
    let dependencies = string_views(&value.dependencies);
    let create: Create = symbol(context, b"codex_agent_skill_create\0")?;
    create_owned(
        context,
        b"codex_agent_skill_destroy\0",
        "skill input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &name,
                &display_name,
                &description,
                &path,
                value.scope as i32,
                i32::from(value.is_enabled),
                i32::from(value.brand_color.is_some()),
                &brand,
                dependencies.as_ptr(),
                dependencies.len(),
                i32::from(value.can_uninstall),
                1,
                value.origin as i32,
                out,
            )
        },
    )
}

fn create_hook_handler<'a>(
    context: &'a Arc<ContextInner>,
    value: &crate::HookHandler,
) -> Result<OwnedValue<'a, ffi::HookHandler>, CodexError> {
    type Acquire<T> = unsafe extern "C" fn(*mut ffi::Context, *mut *mut T) -> i32;
    type From<T> =
        unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut ffi::HookHandler) -> i32;
    type CommandCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        i32,
        *mut *mut ffi::HookHandlerCommand,
    ) -> i32;
    type McpCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        *mut *mut ffi::HookHandlerMcpTool,
    ) -> i32;

    macro_rules! wrap {
        ($concrete:expr, $from_ty:ty, $from_name:literal) => {{
            let concrete = $concrete?;
            let from: From<$from_ty> = symbol(context, concat!($from_name, "\0").as_bytes())?;
            let result = create_owned(
                context,
                b"codex_agent_hook_handler_destroy\0",
                "hook handler input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { from(context.ptr(), concrete.raw(), out) },
            );
            concrete.close()?;
            result
        }};
    }

    match value {
        crate::HookHandler::Agent(_) => {
            let acquire: Acquire<ffi::HookHandlerAgent> =
                symbol(context, b"codex_agent_hook_handler_agent_acquire\0")?;
            wrap!(
                create_owned(
                    context,
                    b"codex_agent_hook_handler_agent_destroy\0",
                    "agent hook handler input",
                    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                    |out| unsafe { acquire(context.ptr(), out) },
                ),
                ffi::HookHandlerAgent,
                "codex_agent_hook_handler_from_agent"
            )
        }
        crate::HookHandler::Prompt(_) => {
            let acquire: Acquire<ffi::HookHandlerPrompt> =
                symbol(context, b"codex_agent_hook_handler_prompt_acquire\0")?;
            wrap!(
                create_owned(
                    context,
                    b"codex_agent_hook_handler_prompt_destroy\0",
                    "prompt hook handler input",
                    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                    |out| unsafe { acquire(context.ptr(), out) },
                ),
                ffi::HookHandlerPrompt,
                "codex_agent_hook_handler_from_prompt"
            )
        }
        crate::HookHandler::Command(value) => {
            let create: CommandCreate =
                symbol(context, b"codex_agent_hook_handler_command_create\0")?;
            let command = ffi::StringView::new(&value.command);
            wrap!(
                create_owned(
                    context,
                    b"codex_agent_hook_handler_command_destroy\0",
                    "command hook handler input",
                    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                    |out| unsafe {
                        create(context.ptr(), &command, i32::from(value.is_async), out)
                    },
                ),
                ffi::HookHandlerCommand,
                "codex_agent_hook_handler_from_command"
            )
        }
        crate::HookHandler::McpTool(value) => {
            let create: McpCreate = symbol(context, b"codex_agent_hook_handler_mcp_tool_create\0")?;
            let server = ffi::StringView::new(&value.server);
            let tool = ffi::StringView::new(&value.tool);
            wrap!(
                create_owned(
                    context,
                    b"codex_agent_hook_handler_mcp_tool_destroy\0",
                    "MCP-tool hook handler input",
                    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                    |out| unsafe { create(context.ptr(), &server, &tool, out) },
                ),
                ffi::HookHandlerMcpTool,
                "codex_agent_hook_handler_from_mcp_tool"
            )
        }
    }
}

fn create_hook<'a>(
    context: &'a Arc<ContextInner>,
    value: &Hook,
) -> Result<OwnedValue<'a, ffi::Hook>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        *mut ffi::HookHandler,
        i32,
        *const ffi::StringView,
        *const ffi::StringView,
        i64,
        i32,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        i32,
        i32,
        *mut *mut ffi::Hook,
    ) -> i32;
    let handler = create_hook_handler(context, &value.handler)?;
    let key = ffi::StringView::new(&value.key);
    let hash = ffi::StringView::new(&value.current_hash);
    let event = ffi::StringView::new(&value.event_name);
    let source = ffi::StringView::new(&value.source);
    let source_path = ffi::StringView::new(&value.source_path);
    let matcher = optional_view(&value.matcher);
    let plugin = optional_view(&value.plugin_id);
    let status = optional_view(&value.status_message);
    let create: Create = symbol(context, b"codex_agent_hook_create\0")?;
    let result = create_owned(
        context,
        b"codex_agent_hook_destroy\0",
        "hook input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &key,
                &hash,
                i32::from(value.is_enabled),
                &event,
                handler.raw(),
                i32::from(value.is_managed),
                &source,
                &source_path,
                value.timeout_seconds,
                value.trust_status as i32,
                i32::from(value.matcher.is_some()),
                &matcher,
                i32::from(value.plugin_id.is_some()),
                &plugin,
                i32::from(value.status_message.is_some()),
                &status,
                1,
                value.origin as i32,
                i32::from(value.can_uninstall),
                out,
            )
        },
    );
    handler.close()?;
    result
}

fn install_hook(
    owner: Arc<ServiceInner<ffi::Hooks>>,
    directory: String,
    scope: InstallationScope,
) -> Result<CodexOperation<Hook>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Hooks,
        *const ffi::StringView,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let start: ExactSymbol<Start> =
        exact_symbol(&owner.handle.context, b"codex_agent_hooks_install\0")?;
    let view = ffi::StringView::new(&directory);
    operation(
        owner,
        b"codex_agent_hooks_install\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |context, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        context.ptr(),
                        service,
                        &view,
                        scope as i32,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |context, operation| {
            operation_value(
                context,
                operation,
                b"codex_agent_operation_hook\0",
                decode_hook,
            )
        },
    )
}

fn hook_operation(
    owner: Arc<ServiceInner<ffi::Hooks>>,
    hook: &Hook,
    name: &'static [u8],
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Hooks,
        *mut ffi::Hook,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_hook(&context, hook)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, name)?;
    let result = operation(
        owner,
        name,
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    );
    input.close()?;
    result
}

fn model_effort(
    owner: Arc<ServiceInner<ffi::Models>>,
    model: &Model,
    resolution: Resolution,
) -> Result<CodexOperation<String>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Models,
        *mut ffi::Model,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    type Copy = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Operation,
        *mut u8,
        usize,
        *mut usize,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_model(&context, model)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, b"codex_agent_models_resolve_effort\0")?;
    let result = operation(
        owner,
        b"codex_agent_models_resolve_effort\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        raw,
                        resolution as i32,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |current, operation| {
            let copy: ExactSymbol<Copy> =
                exact_symbol(current, b"codex_agent_operation_string_copy\0")?;
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            copy_string(|buffer, capacity, required| {
                copy.invoke(|call| {
                    ffi_call! {
                        call(current.ptr(), operation, buffer, capacity, required)
                    }
                })
            })
        },
    );
    input.close()?;
    result
}

fn model_service_tier(
    owner: Arc<ServiceInner<ffi::Models>>,
    model: &Model,
    resolution: Resolution,
) -> Result<CodexOperation<Option<ServiceTier>>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Models,
        *mut ffi::Model,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    type Has = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Operation, *mut i32) -> i32;
    let context = owner.handle.context.clone();
    let input = create_model(&context, model)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> =
        exact_symbol(&context, b"codex_agent_models_resolve_service_tier\0")?;
    let result = operation(
        owner,
        b"codex_agent_models_resolve_service_tier\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        raw,
                        resolution as i32,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |current, operation| {
            let has: ExactSymbol<Has> =
                exact_symbol(current, b"codex_agent_operation_has_service_tier\0")?;
            let mut present = 0;
            check(
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                has.invoke(|call| {
                    ffi_call! {
                        call(current.ptr(), operation, &mut present)
                    }
                }),
                "read optional service tier",
            )?;
            if present == 0 {
                Ok(None)
            } else {
                operation_value(
                    current,
                    operation,
                    b"codex_agent_operation_service_tier\0",
                    decode_service_tier,
                )
                .map(Some)
            }
        },
    );
    input.close()?;
    result
}

fn plugin_list(
    owner: Arc<ServiceInner<ffi::Plugins>>,
    force_reload: bool,
) -> Result<CodexOperation<PluginCatalog>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Plugins,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let start: ExactSymbol<Start> =
        exact_symbol(&owner.handle.context, b"codex_agent_plugins_list\0")?;
    operation(
        owner,
        b"codex_agent_plugins_list\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        i32::from(force_reload),
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |current, operation| {
            operation_value(
                current,
                operation,
                b"codex_agent_operation_plugin_catalog\0",
                decode_plugin_catalog,
            )
        },
    )
}

fn plugin_operation<V: 'static, R: 'static>(
    owner: Arc<ServiceInner<ffi::Plugins>>,
    plugin: &PluginReference,
    start_name: &'static [u8],
    result_name: &'static [u8],
    decoder: fn(&Arc<ContextInner>, *mut V) -> Result<R, CodexError>,
) -> Result<CodexOperation<R>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Plugins,
        *mut ffi::PluginReference,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_plugin_reference(&context, plugin)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, start_name)?;
    let result = operation(
        owner,
        start_name,
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        move |current, operation| operation_value(current, operation, result_name, decoder),
    );
    input.close()?;
    result
}

fn plugin_unit(
    owner: Arc<ServiceInner<ffi::Plugins>>,
    plugin: &PluginReference,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Plugins,
        *mut ffi::PluginReference,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_plugin_reference(&context, plugin)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, b"codex_agent_plugins_uninstall\0")?;
    let result = operation(
        owner,
        b"codex_agent_plugins_uninstall\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    );
    input.close()?;
    result
}

fn skill_list(
    owner: Arc<ServiceInner<ffi::Skills>>,
    force_reload: bool,
) -> Result<CodexOperation<SkillCatalog>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Skills,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let start: ExactSymbol<Start> =
        exact_symbol(&owner.handle.context, b"codex_agent_skills_list\0")?;
    operation(
        owner,
        b"codex_agent_skills_list\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        i32::from(force_reload),
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |current, operation| {
            operation_value(
                current,
                operation,
                b"codex_agent_operation_skill_catalog\0",
                decode_skill_catalog,
            )
        },
    )
}

fn skill_read(
    owner: Arc<ServiceInner<ffi::Skills>>,
    path: String,
    offset: i64,
) -> Result<CodexOperation<SkillChunk>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Skills,
        *const ffi::StringView,
        i64,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let start: ExactSymbol<Start> =
        exact_symbol(&owner.handle.context, b"codex_agent_skills_read\0")?;
    let view = ffi::StringView::new(&path);
    operation(
        owner,
        b"codex_agent_skills_read\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        &view,
                        offset,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |current, operation| {
            operation_value(
                current,
                operation,
                b"codex_agent_operation_skill_chunk\0",
                decode_skill_chunk,
            )
        },
    )
}

fn skill_install(
    owner: Arc<ServiceInner<ffi::Skills>>,
    directory: String,
    scope: InstallationScope,
) -> Result<CodexOperation<Skill>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Skills,
        *const ffi::StringView,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let start: ExactSymbol<Start> =
        exact_symbol(&owner.handle.context, b"codex_agent_skills_install\0")?;
    let view = ffi::StringView::new(&directory);
    operation(
        owner,
        b"codex_agent_skills_install\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        &view,
                        scope as i32,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |current, operation| {
            operation_value(
                current,
                operation,
                b"codex_agent_operation_skill\0",
                decode_skill,
            )
        },
    )
}

fn skill_uninstall(
    owner: Arc<ServiceInner<ffi::Skills>>,
    skill: &Skill,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Skills,
        *mut ffi::Skill,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_skill(&context, skill)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, b"codex_agent_skills_uninstall\0")?;
    let result = operation(
        owner,
        b"codex_agent_skills_uninstall\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    );
    input.close()?;
    result
}

fn create_mcp_environment_variable<'a>(
    context: &'a Arc<ContextInner>,
    value: &crate::McpEnvironmentVariable,
) -> Result<OwnedValue<'a, ffi::McpEnvironmentVariable>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        i32,
        i32,
        *mut *mut ffi::McpEnvironmentVariable,
    ) -> i32;
    let name = ffi::StringView::new(&value.name);
    let create: Create = symbol(context, b"codex_agent_mcp_environment_variable_create\0")?;
    create_owned(
        context,
        b"codex_agent_mcp_environment_variable_destroy\0",
        "MCP environment input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &name,
                i32::from(value.source.is_some()),
                value.source.map_or(0, |source| source as i32),
                out,
            )
        },
    )
}

fn create_mcp_oauth<'a>(
    context: &'a Arc<ContextInner>,
    value: &crate::McpOauthConfiguration,
) -> Result<OwnedValue<'a, ffi::McpOauthConfiguration>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        i32,
        *const ffi::StringView,
        i32,
        i32,
        *mut *mut ffi::McpOauthConfiguration,
    ) -> i32;
    let client_id = optional_view(&value.client_id);
    let create: Create = symbol(context, b"codex_agent_mcp_oauth_configuration_create\0")?;
    create_owned(
        context,
        b"codex_agent_mcp_oauth_configuration_destroy\0",
        "MCP OAuth input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                i32::from(value.client_id.is_some()),
                &client_id,
                i32::from(value.callback_port.is_some()),
                value.callback_port.unwrap_or(0),
                out,
            )
        },
    )
}

fn create_mcp_tool<'a>(
    context: &'a Arc<ContextInner>,
    value: &crate::McpToolConfiguration,
) -> Result<OwnedValue<'a, ffi::McpToolConfiguration>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        i32,
        i32,
        *mut *mut ffi::McpToolConfiguration,
    ) -> i32;
    let create: Create = symbol(context, b"codex_agent_mcp_tool_configuration_create\0")?;
    create_owned(
        context,
        b"codex_agent_mcp_tool_configuration_destroy\0",
        "MCP tool input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                i32::from(value.approval.is_some()),
                value.approval.map_or(0, |approval| approval as i32),
                out,
            )
        },
    )
}

fn map_views(
    values: &Option<std::collections::BTreeMap<String, String>>,
) -> (Vec<ffi::StringView>, Vec<ffi::StringView>) {
    values.as_ref().map_or_else(
        || (Vec::new(), Vec::new()),
        |values| {
            (
                values.keys().map(|key| ffi::StringView::new(key)).collect(),
                values
                    .values()
                    .map(|value| ffi::StringView::new(value))
                    .collect(),
            )
        },
    )
}

fn create_mcp_transport<'a>(
    context: &'a Arc<ContextInner>,
    value: &crate::McpTransport,
) -> Result<OwnedValue<'a, ffi::McpTransport>, CodexError> {
    type HttpCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        *const ffi::StringView,
        usize,
        i32,
        *const ffi::StringView,
        *const ffi::StringView,
        usize,
        i32,
        *const ffi::StringView,
        *mut *mut ffi::McpTransportHttp,
    ) -> i32;
    type StdioCreate = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        usize,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        *const ffi::StringView,
        usize,
        *const *mut ffi::McpEnvironmentVariable,
        usize,
        *mut *mut ffi::McpTransportStdio,
    ) -> i32;
    type Wrap<T> =
        unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut ffi::McpTransport) -> i32;

    match value {
        crate::McpTransport::Http(value) => {
            let url = ffi::StringView::new(&value.url);
            let bearer = optional_view(&value.bearer_token_environment_variable);
            let (header_keys, header_values) = map_views(&value.headers);
            let (environment_keys, environment_values) = map_views(&value.environment_headers);
            let helper = optional_view(&value.headers_helper);
            let create: HttpCreate = symbol(context, b"codex_agent_mcp_transport_http_create\0")?;
            let concrete = create_owned(
                context,
                b"codex_agent_mcp_transport_http_destroy\0",
                "MCP HTTP transport input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe {
                    create(
                        context.ptr(),
                        &url,
                        i32::from(value.bearer_token_environment_variable.is_some()),
                        &bearer,
                        i32::from(value.headers.is_some()),
                        header_keys.as_ptr(),
                        header_values.as_ptr(),
                        header_keys.len(),
                        i32::from(value.environment_headers.is_some()),
                        environment_keys.as_ptr(),
                        environment_values.as_ptr(),
                        environment_keys.len(),
                        i32::from(value.headers_helper.is_some()),
                        &helper,
                        out,
                    )
                },
            )?;
            let wrap: Wrap<ffi::McpTransportHttp> =
                symbol(context, b"codex_agent_mcp_transport_from_http\0")?;
            let result = create_owned(
                context,
                b"codex_agent_mcp_transport_destroy\0",
                "MCP transport input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { wrap(context.ptr(), concrete.raw(), out) },
            );
            concrete.close()?;
            result
        }
        crate::McpTransport::Stdio(value) => {
            let command = ffi::StringView::new(&value.command);
            let arguments = string_views(&value.arguments);
            let working_directory = optional_view(&value.working_directory);
            let (environment_keys, environment_values) = map_views(&value.environment);
            let forwarded: Vec<_> = value
                .forwarded_environment
                .iter()
                .map(|item| create_mcp_environment_variable(context, item))
                .collect::<Result<_, _>>()?;
            let forwarded_handles: Vec<_> = forwarded.iter().map(OwnedValue::raw).collect();
            let create: StdioCreate = symbol(context, b"codex_agent_mcp_transport_stdio_create\0")?;
            let concrete = create_owned(
                context,
                b"codex_agent_mcp_transport_stdio_destroy\0",
                "MCP stdio transport input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe {
                    create(
                        context.ptr(),
                        &command,
                        arguments.as_ptr(),
                        arguments.len(),
                        i32::from(value.working_directory.is_some()),
                        &working_directory,
                        i32::from(value.environment.is_some()),
                        environment_keys.as_ptr(),
                        environment_values.as_ptr(),
                        environment_keys.len(),
                        forwarded_handles.as_ptr(),
                        forwarded_handles.len(),
                        out,
                    )
                },
            )?;
            let wrap: Wrap<ffi::McpTransportStdio> =
                symbol(context, b"codex_agent_mcp_transport_from_stdio\0")?;
            let result = create_owned(
                context,
                b"codex_agent_mcp_transport_destroy\0",
                "MCP transport input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { wrap(context.ptr(), concrete.raw(), out) },
            );
            concrete.close()?;
            result
        }
    }
}

fn create_mcp_configuration<'a>(
    context: &'a Arc<ContextInner>,
    value: &McpServerConfiguration,
) -> Result<OwnedValue<'a, ffi::McpServerConfiguration>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *mut ffi::McpTransport,
        i32,
        i32,
        *const ffi::StringView,
        i32,
        i32,
        i32,
        i32,
        *const i32,
        usize,
        i32,
        f64,
        i32,
        f64,
        i32,
        i32,
        i32,
        *const ffi::StringView,
        usize,
        i32,
        *const ffi::StringView,
        usize,
        i32,
        *const ffi::StringView,
        usize,
        i32,
        *mut ffi::McpOauthConfiguration,
        i32,
        *const ffi::StringView,
        *const ffi::StringView,
        *const *mut ffi::McpToolConfiguration,
        usize,
        *mut *mut ffi::McpServerConfiguration,
    ) -> i32;
    let transport = create_mcp_transport(context, &value.transport)?;
    let oauth = value
        .oauth
        .as_ref()
        .map(|oauth| create_mcp_oauth(context, oauth))
        .transpose()?;
    let tools: Vec<_> = value
        .tools
        .values()
        .map(|tool| create_mcp_tool(context, tool))
        .collect::<Result<_, _>>()?;
    let tool_handles: Vec<_> = tools.iter().map(OwnedValue::raw).collect();
    let name = ffi::StringView::new(&value.name);
    let environment = ffi::StringView::new(&value.environment_id);
    let omit: Vec<_> = value
        .omit_tools_from
        .as_deref()
        .unwrap_or_default()
        .iter()
        .map(|value| *value as i32)
        .collect();
    let enabled = string_views(value.enabled_tools.as_deref().unwrap_or_default());
    let disabled = string_views(value.disabled_tools.as_deref().unwrap_or_default());
    let scopes = string_views(value.scopes.as_deref().unwrap_or_default());
    let oauth_resource = optional_view(&value.oauth_resource);
    let tool_keys: Vec<_> = value
        .tools
        .keys()
        .map(|key| ffi::StringView::new(key))
        .collect();
    let create: Create = symbol(context, b"codex_agent_mcp_server_configuration_create\0")?;
    let result = create_owned(
        context,
        b"codex_agent_mcp_server_configuration_destroy\0",
        "MCP configuration input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &name,
                transport.raw(),
                i32::from(value.authentication.is_some()),
                value.authentication.map_or(0, |item| item as i32),
                &environment,
                i32::from(value.is_enabled),
                i32::from(value.is_required),
                i32::from(value.supports_parallel_tool_calls),
                i32::from(value.omit_tools_from.is_some()),
                omit.as_ptr(),
                omit.len(),
                i32::from(value.startup_timeout_seconds.is_some()),
                value.startup_timeout_seconds.unwrap_or(0.0),
                i32::from(value.tool_timeout_seconds.is_some()),
                value.tool_timeout_seconds.unwrap_or(0.0),
                i32::from(value.default_tool_approval.is_some()),
                value.default_tool_approval.map_or(0, |item| item as i32),
                i32::from(value.enabled_tools.is_some()),
                enabled.as_ptr(),
                enabled.len(),
                i32::from(value.disabled_tools.is_some()),
                disabled.as_ptr(),
                disabled.len(),
                i32::from(value.scopes.is_some()),
                scopes.as_ptr(),
                scopes.len(),
                i32::from(oauth.is_some()),
                oauth.as_ref().map_or(std::ptr::null_mut(), OwnedValue::raw),
                i32::from(value.oauth_resource.is_some()),
                &oauth_resource,
                tool_keys.as_ptr(),
                tool_handles.as_ptr(),
                tool_handles.len(),
                out,
            )
        },
    );
    transport.close()?;
    if let Some(oauth) = oauth {
        oauth.close()?;
    }
    result
}

fn create_mcp_server<'a>(
    context: &'a Arc<ContextInner>,
    value: &McpServer,
) -> Result<OwnedValue<'a, ffi::McpServer>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        i32,
        *mut ffi::McpServerConfiguration,
        i32,
        i32,
        *mut *mut ffi::McpServer,
    ) -> i32;
    let configuration = value
        .configuration
        .as_ref()
        .map(|value| create_mcp_configuration(context, value))
        .transpose()?;
    let name = ffi::StringView::new(&value.name);
    let display_name = ffi::StringView::new(&value.display_name);
    let create: Create = symbol(context, b"codex_agent_mcp_server_create\0")?;
    let result = create_owned(
        context,
        b"codex_agent_mcp_server_destroy\0",
        "MCP server input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &name,
                &display_name,
                value.auth_status as i32,
                configuration
                    .as_ref()
                    .map_or(std::ptr::null_mut(), OwnedValue::raw),
                value.origin as i32,
                i32::from(value.can_remove),
                out,
            )
        },
    );
    if let Some(configuration) = configuration {
        configuration.close()?;
    }
    result
}

fn mcp_add(
    owner: Arc<ServiceInner<ffi::McpServers>>,
    configuration: &McpServerConfiguration,
) -> Result<CodexOperation<McpServer>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::McpServers,
        *mut ffi::McpServerConfiguration,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_mcp_configuration(&context, configuration)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, b"codex_agent_mcp_servers_add\0")?;
    let result = operation(
        owner,
        b"codex_agent_mcp_servers_add\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |current, operation| {
            operation_value(
                current,
                operation,
                b"codex_agent_operation_mcp_server\0",
                decode_mcp_server,
            )
        },
    );
    input.close()?;
    result
}

fn mcp_remove(
    owner: Arc<ServiceInner<ffi::McpServers>>,
    server: &McpServer,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::McpServers,
        *mut ffi::McpServer,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_mcp_server(&context, server)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(&context, b"codex_agent_mcp_servers_remove\0")?;
    let result = operation(
        owner,
        b"codex_agent_mcp_servers_remove\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    );
    input.close()?;
    result
}

fn create_connector<'a>(
    context: &'a Arc<ContextInner>,
    value: &Connector,
) -> Result<OwnedValue<'a, ffi::Connector>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        i32,
        *const ffi::StringView,
        usize,
        *mut *mut ffi::Connector,
    ) -> i32;
    let id = ffi::StringView::new(&value.id);
    let name = ffi::StringView::new(&value.name);
    let description = ffi::StringView::new(&value.description);
    let install_url = optional_view(&value.install_url);
    let plugin_names = string_views(&value.plugin_names);
    let create: Create = symbol(context, b"codex_agent_connector_create\0")?;
    create_owned(
        context,
        b"codex_agent_connector_destroy\0",
        "connector input",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        |out| unsafe {
            create(
                context.ptr(),
                &id,
                &name,
                &description,
                i32::from(value.install_url.is_some()),
                &install_url,
                i32::from(value.is_accessible),
                i32::from(value.is_enabled),
                plugin_names.as_ptr(),
                plugin_names.len(),
                out,
            )
        },
    )
}

fn create_integration<'a>(
    context: &'a Arc<ContextInner>,
    value: &Integration,
) -> Result<OwnedValue<'a, ffi::Integration>, CodexError> {
    type ConcreteCreate<T, U> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut U) -> i32;
    type Wrap<T> =
        unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut ffi::Integration) -> i32;
    match value {
        Integration::Connector(value) => {
            let item = create_connector(context, &value.connector)?;
            let create: ConcreteCreate<ffi::Connector, ffi::IntegrationConnector> =
                symbol(context, b"codex_agent_integration_connector_create\0")?;
            let concrete = create_owned(
                context,
                b"codex_agent_integration_connector_destroy\0",
                "connector integration input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { create(context.ptr(), item.raw(), out) },
            )?;
            item.close()?;
            let wrap: Wrap<ffi::IntegrationConnector> =
                symbol(context, b"codex_agent_integration_from_connector\0")?;
            let result = create_owned(
                context,
                b"codex_agent_integration_destroy\0",
                "integration input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { wrap(context.ptr(), concrete.raw(), out) },
            );
            concrete.close()?;
            result
        }
        Integration::McpServer(value) => {
            let item = create_mcp_server(context, &value.server)?;
            let create: ConcreteCreate<ffi::McpServer, ffi::IntegrationMcpServer> =
                symbol(context, b"codex_agent_integration_mcp_server_create\0")?;
            let concrete = create_owned(
                context,
                b"codex_agent_integration_mcp_server_destroy\0",
                "MCP integration input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { create(context.ptr(), item.raw(), out) },
            )?;
            item.close()?;
            let wrap: Wrap<ffi::IntegrationMcpServer> =
                symbol(context, b"codex_agent_integration_from_mcp_server\0")?;
            let result = create_owned(
                context,
                b"codex_agent_integration_destroy\0",
                "integration input",
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                |out| unsafe { wrap(context.ptr(), concrete.raw(), out) },
            );
            concrete.close()?;
            result
        }
    }
}

fn decode_integration(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Integration,
) -> Result<Integration, CodexError> {
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_integration_destroy\0",
        "integration",
    )?;
    let result = match scalar_i32(context, owned.raw(), b"codex_agent_integration_kind\0")? {
        0 => {
            let concrete: *mut ffi::IntegrationConnector =
                child(context, owned.raw(), b"codex_agent_integration_connector\0")?;
            let concrete = OwnedValue::new(
                context,
                concrete,
                b"codex_agent_integration_connector_destroy\0",
                "connector integration",
            )?;
            let connector = decode_connector(
                context,
                child(
                    context,
                    concrete.raw(),
                    b"codex_agent_integration_connector_connector\0",
                )?,
            )?;
            concrete.close()?;
            Integration::Connector(crate::ConnectorIntegration::new(connector))
        }
        1 => {
            let concrete: *mut ffi::IntegrationMcpServer = child(
                context,
                owned.raw(),
                b"codex_agent_integration_mcp_server\0",
            )?;
            let concrete = OwnedValue::new(
                context,
                concrete,
                b"codex_agent_integration_mcp_server_destroy\0",
                "MCP integration",
            )?;
            let server = decode_mcp_server(
                context,
                child(
                    context,
                    concrete.raw(),
                    b"codex_agent_integration_mcp_server_server\0",
                )?,
            )?;
            concrete.close()?;
            Integration::McpServer(Box::new(crate::McpServerIntegration::new(server)))
        }
        _ => {
            return Err(CodexError::new(
                Status::InternalError,
                "unknown integration kind",
            ));
        }
    };
    owned.close()?;
    Ok(result)
}

fn decode_integration_authorization_snapshot(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
) -> Result<IntegrationAuthorizationState, CodexError> {
    let raw: *mut ffi::IntegrationAuthorizationState = child(
        context,
        snapshot,
        b"codex_agent_integration_authorization_state_value\0",
    )?;
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_integration_authorization_state_destroy\0",
        "integration authorization state",
    )?;
    let status = crate::IntegrationAuthorizationStatus::from_raw(scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_integration_authorization_state_status\0",
    )?)
    .ok_or_else(|| CodexError::new(Status::InternalError, "unknown authorization status"))?;
    type Optional<T, U> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut U) -> i32;
    let target_get: Optional<ffi::IntegrationAuthorizationState, ffi::Integration> = symbol(
        context,
        b"codex_agent_integration_authorization_state_target\0",
    )?;
    let mut target_raw = std::ptr::null_mut();
    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
    let target_status = unsafe { target_get(context.ptr(), owned.raw(), &mut target_raw) };
    let target = if target_status == ffi::STATUS_OK {
        Some(decode_integration(context, target_raw)?)
    } else if target_status == 13 {
        None
    } else {
        check(target_status, "read authorization target")?;
        unreachable!()
    };
    let failure_get: Optional<ffi::IntegrationAuthorizationState, ffi::Failure> = symbol(
        context,
        b"codex_agent_integration_authorization_state_failure\0",
    )?;
    let mut failure_raw = std::ptr::null_mut();
    // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
    let failure_status = unsafe { failure_get(context.ptr(), owned.raw(), &mut failure_raw) };
    let failure = if failure_status == ffi::STATUS_OK {
        Some(read_failure(context, failure_raw)?)
    } else if failure_status == 13 {
        None
    } else {
        check(failure_status, "read authorization failure")?;
        unreachable!()
    };
    owned.close()?;
    Ok(IntegrationAuthorizationState::new(status, target, failure))
}

fn decode_active_integration_snapshot(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
) -> Result<Option<Integration>, CodexError> {
    if scalar_i32(
        context,
        snapshot,
        b"codex_agent_integration_authorization_active_has_value\0",
    )? == 0
    {
        Ok(None)
    } else {
        decode_integration(
            context,
            child(
                context,
                snapshot,
                b"codex_agent_integration_authorization_active_value\0",
            )?,
        )
        .map(Some)
    }
}

fn authorize_integration(
    owner: Arc<ServiceInner<ffi::IntegrationAuthorization>>,
    target: &Integration,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::IntegrationAuthorization,
        *mut ffi::Integration,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let context = owner.handle.context.clone();
    let input = create_integration(&context, target)?;
    let raw = input.raw();
    let start: ExactSymbol<Start> = exact_symbol(
        &context,
        b"codex_agent_integration_authorization_authorize\0",
    )?;
    let result = operation(
        owner,
        b"codex_agent_integration_authorization_authorize\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(current.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    );
    input.close()?;
    result
}

fn optional_i64<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    name: &'static [u8],
) -> Result<Option<i64>, CodexError> {
    type Getter<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32, *mut i64) -> i32;
    let getter: Getter<T> = symbol(context, name)?;
    let mut present = 0;
    let mut value = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { getter(context.ptr(), raw, &mut present, &mut value) },
        "read optional i64",
    )?;
    Ok((present != 0).then_some(value))
}

fn optional_f64<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    name: &'static [u8],
) -> Result<Option<f64>, CodexError> {
    type Getter<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32, *mut f64) -> i32;
    let getter: Getter<T> = symbol(context, name)?;
    let mut present = 0;
    let mut value = 0.0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { getter(context.ptr(), raw, &mut present, &mut value) },
        "read optional f64",
    )?;
    if present != 0 && !value.is_finite() {
        return Err(CodexError::new(
            Status::InternalError,
            "native form bound is non-finite",
        ));
    }
    Ok((present != 0).then_some(value))
}

fn decode_form_field(
    context: &Arc<ContextInner>,
    raw: *mut ffi::FormField,
) -> Result<crate::FormField, CodexError> {
    type Count = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::FormField, *mut usize) -> i32;
    type At = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::FormField,
        usize,
        *mut *mut ffi::FormOption,
    ) -> i32;
    type Format =
        unsafe extern "C" fn(*mut ffi::Context, *mut ffi::FormField, *mut i32, *mut i32) -> i32;
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_form_field_destroy\0",
        "form field",
    )?;
    let count: Count = symbol(context, b"codex_agent_form_field_options_count\0")?;
    let at: At = symbol(context, b"codex_agent_form_field_option_at\0")?;
    let mut length = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { count(context.ptr(), owned.raw(), &mut length) },
        "read form options count",
    )?;
    let mut options = Vec::with_capacity(length);
    for index in 0..length {
        let mut option = std::ptr::null_mut();
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { at(context.ptr(), owned.raw(), index, &mut option) },
            "read form option",
        )?;
        options.push(decode_form_option(context, option)?);
    }
    let default_value = if scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_form_field_has_default_value\0",
    )? == 0
    {
        None
    } else {
        Some(decode_form_value(
            context,
            child(
                context,
                owned.raw(),
                b"codex_agent_form_field_default_value\0",
            )?,
        )?)
    };
    let format_get: Format = symbol(context, b"codex_agent_form_field_format\0")?;
    let mut has_format = 0;
    let mut raw_format = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { format_get(context.ptr(), owned.raw(), &mut has_format, &mut raw_format) },
        "read form format",
    )?;
    let description = if scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_form_field_has_description\0",
    )? == 0
    {
        None
    } else {
        Some(native_string(
            context,
            owned.raw(),
            b"codex_agent_form_field_description_copy\0",
        )?)
    };
    let result = crate::FormField::new(
        native_string(context, owned.raw(), b"codex_agent_form_field_name_copy\0")?,
        native_string(context, owned.raw(), b"codex_agent_form_field_title_copy\0")?,
        description,
        scalar_i32(
            context,
            owned.raw(),
            b"codex_agent_form_field_is_required\0",
        )? != 0,
        crate::FormFieldType::from_raw(scalar_i32(
            context,
            owned.raw(),
            b"codex_agent_form_field_type\0",
        )?)
        .ok_or_else(|| CodexError::new(Status::InternalError, "unknown form field type"))?,
        options,
        default_value,
        optional_f64(context, owned.raw(), b"codex_agent_form_field_minimum\0")?,
        optional_f64(context, owned.raw(), b"codex_agent_form_field_maximum\0")?,
        if has_format == 0 {
            None
        } else {
            Some(
                crate::FormStringFormat::from_raw(raw_format).ok_or_else(|| {
                    CodexError::new(Status::InternalError, "unknown form string format")
                })?,
            )
        },
        optional_i64(
            context,
            owned.raw(),
            b"codex_agent_form_field_minimum_length\0",
        )?,
        optional_i64(
            context,
            owned.raw(),
            b"codex_agent_form_field_maximum_length\0",
        )?,
        optional_i64(
            context,
            owned.raw(),
            b"codex_agent_form_field_minimum_selections\0",
        )?,
        optional_i64(
            context,
            owned.raw(),
            b"codex_agent_form_field_maximum_selections\0",
        )?,
        scalar_i32(
            context,
            owned.raw(),
            b"codex_agent_form_field_allows_other\0",
        )? != 0,
        scalar_i32(context, owned.raw(), b"codex_agent_form_field_is_secret\0")? != 0,
    )?;
    owned.close()?;
    Ok(result)
}

fn decode_elicitation(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Elicitation,
) -> Result<crate::Elicitation, CodexError> {
    type Count = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Elicitation, *mut usize) -> i32;
    type At = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Elicitation,
        usize,
        *mut *mut ffi::FormField,
    ) -> i32;
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_elicitation_destroy\0",
        "elicitation",
    )?;
    let form = if scalar_i32(context, owned.raw(), b"codex_agent_elicitation_has_form\0")? == 0 {
        None
    } else {
        let count: Count = symbol(context, b"codex_agent_elicitation_form_count\0")?;
        let at: At = symbol(context, b"codex_agent_elicitation_form_at\0")?;
        let mut length = 0;
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { count(context.ptr(), owned.raw(), &mut length) },
            "read elicitation form count",
        )?;
        let mut fields = Vec::with_capacity(length);
        for index in 0..length {
            let mut field = std::ptr::null_mut();
            check(
                // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
                unsafe { at(context.ptr(), owned.raw(), index, &mut field) },
                "read elicitation form field",
            )?;
            fields.push(decode_form_field(context, field)?);
        }
        Some(fields)
    };
    let url = if scalar_i32(context, owned.raw(), b"codex_agent_elicitation_has_url\0")? == 0 {
        None
    } else {
        Some(native_string(
            context,
            owned.raw(),
            b"codex_agent_elicitation_url_copy\0",
        )?)
    };
    let value = crate::Elicitation::new(
        native_string(
            context,
            owned.raw(),
            b"codex_agent_elicitation_request_id_copy\0",
        )?,
        native_string(
            context,
            owned.raw(),
            b"codex_agent_elicitation_server_name_copy\0",
        )?,
        decode_conversation_id(
            context,
            child(
                context,
                owned.raw(),
                b"codex_agent_elicitation_conversation_id\0",
            )?,
        )?,
        native_string(
            context,
            owned.raw(),
            b"codex_agent_elicitation_message_copy\0",
        )?,
        form,
        url,
    );
    owned.close()?;
    Ok(value)
}

fn retain_approval(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PendingApproval,
    owner: &Arc<ServiceInner<ffi::Interactions>>,
) -> Result<PendingApproval, CodexError> {
    let identity = Arc::new(crate::residual_values::BindingIdentity);
    let value = PendingApproval::new(
        native_string(
            context,
            raw,
            b"codex_agent_pending_approval_request_id_copy\0",
        )?,
        decode_conversation_id(
            context,
            child(
                context,
                raw,
                b"codex_agent_pending_approval_conversation_id\0",
            )?,
        )?,
        native_string(context, raw, b"codex_agent_pending_approval_title_copy\0")?,
        native_string(context, raw, b"codex_agent_pending_approval_details_copy\0")?,
    )
    .with_binding_identity(identity.clone());
    owner
        .pending
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .push(RetainedPending::Approval {
            identity,
            handle: OwnedHandle::new(
                context.clone(),
                raw,
                release_pending_approval,
                "pending approval",
            ),
        });
    Ok(value)
}

fn retain_elicitation(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PendingElicitation,
    owner: &Arc<ServiceInner<ffi::Interactions>>,
) -> Result<PendingElicitation, CodexError> {
    let identity = Arc::new(crate::residual_values::BindingIdentity);
    let value = PendingElicitation::new(decode_elicitation(
        context,
        child(
            context,
            raw,
            b"codex_agent_pending_elicitation_elicitation\0",
        )?,
    )?)
    .with_binding_identity(identity.clone());
    owner
        .pending
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .push(RetainedPending::Elicitation {
            identity,
            handle: OwnedHandle::new(
                context.clone(),
                raw,
                release_pending_elicitation,
                "pending elicitation",
            ),
        });
    Ok(value)
}

fn snapshot_items<T, V>(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
    count_name: &'static [u8],
    at_name: &'static [u8],
    mut decoder: impl FnMut(*mut V) -> Result<T, CodexError>,
) -> Result<Vec<T>, CodexError> {
    type Count = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, *mut usize) -> i32;
    type At<V> =
        unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, usize, *mut *mut V) -> i32;
    let count: ExactSymbol<Count> = exact_symbol(context, count_name)?;
    let at: ExactSymbol<At<V>> = exact_symbol(context, at_name)?;
    let mut length = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        count.invoke(|call| {
            ffi_call! {
                call(context.ptr(), snapshot, &mut length)
            }
        }),
        "read interaction state count",
    )?;
    let mut result = Vec::with_capacity(length);
    for index in 0..length {
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            at.invoke(|call| {
                ffi_call! {
                    call(context.ptr(), snapshot, index, &mut raw)
                }
            }),
            "read interaction state item",
        )?;
        result.push(decoder(raw)?);
    }
    Ok(result)
}

fn decode_approvals_snapshot(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
    owner: &Arc<ServiceInner<ffi::Interactions>>,
) -> Result<Vec<PendingApproval>, CodexError> {
    snapshot_items(
        context,
        snapshot,
        b"codex_agent_interactions_approvals_count\0",
        b"codex_agent_interactions_approvals_at\0",
        |raw| retain_approval(context, raw, owner),
    )
}

fn decode_elicitations_snapshot(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
    owner: &Arc<ServiceInner<ffi::Interactions>>,
) -> Result<Vec<PendingElicitation>, CodexError> {
    snapshot_items(
        context,
        snapshot,
        b"codex_agent_interactions_elicitations_count\0",
        b"codex_agent_interactions_elicitations_at\0",
        |raw| retain_elicitation(context, raw, owner),
    )
}

fn decode_interaction(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PendingInteraction,
    owner: &Arc<ServiceInner<ffi::Interactions>>,
) -> Result<crate::PendingInteraction, CodexError> {
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_pending_interaction_destroy\0",
        "pending interaction",
    )?;
    let result = match scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_pending_interaction_kind\0",
    )? {
        0 => crate::PendingInteraction::Approval(retain_approval(
            context,
            child(
                context,
                owned.raw(),
                b"codex_agent_pending_interaction_approval\0",
            )?,
            owner,
        )?),
        1 => crate::PendingInteraction::Elicitation(retain_elicitation(
            context,
            child(
                context,
                owned.raw(),
                b"codex_agent_pending_interaction_elicitation\0",
            )?,
            owner,
        )?),
        _ => {
            return Err(CodexError::new(
                Status::InternalError,
                "unknown pending interaction kind",
            ));
        }
    };
    owned.close()?;
    Ok(result)
}

fn decode_interaction_state_snapshot(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
    owner: &Arc<ServiceInner<ffi::Interactions>>,
) -> Result<InteractionState, CodexError> {
    type Count =
        unsafe extern "C" fn(*mut ffi::Context, *mut ffi::InteractionState, *mut usize) -> i32;
    type At = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::InteractionState,
        usize,
        *mut *mut ffi::PendingInteraction,
    ) -> i32;
    type Contains = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::InteractionState,
        *const ffi::StringView,
        *mut i32,
    ) -> i32;
    let raw: *mut ffi::InteractionState =
        child(context, snapshot, b"codex_agent_interactions_state_value\0")?;
    let owned = OwnedValue::new(
        context,
        raw,
        b"codex_agent_interaction_state_destroy\0",
        "interaction state",
    )?;
    let count: Count = symbol(context, b"codex_agent_interaction_state_pending_count\0")?;
    let at: At = symbol(context, b"codex_agent_interaction_state_pending_at\0")?;
    let mut length = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { count(context.ptr(), owned.raw(), &mut length) },
        "read pending interaction count",
    )?;
    let mut pending = Vec::with_capacity(length);
    for index in 0..length {
        let mut item = std::ptr::null_mut();
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { at(context.ptr(), owned.raw(), index, &mut item) },
            "read pending interaction",
        )?;
        pending.push(decode_interaction(context, item, owner)?);
    }
    let contains: Contains = symbol(
        context,
        b"codex_agent_interaction_state_resolving_request_ids_contains\0",
    )?;
    let mut resolving = std::collections::BTreeSet::new();
    for item in &pending {
        let view = ffi::StringView::new(item.request_id());
        let mut present = 0;
        check(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { contains(context.ptr(), owned.raw(), &view, &mut present) },
            "read resolving membership",
        )?;
        if present != 0 {
            resolving.insert(item.request_id().to_owned());
        }
    }
    let resolving_count: Count = symbol(
        context,
        b"codex_agent_interaction_state_resolving_request_ids_count\0",
    )?;
    let mut native_resolving_count = 0;
    check(
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        unsafe { resolving_count(context.ptr(), owned.raw(), &mut native_resolving_count) },
        "read resolving count",
    )?;
    if resolving.len() != native_resolving_count {
        return Err(CodexError::new(
            Status::InternalError,
            "unrepresented resolving interaction identity",
        ));
    }
    let failure = if scalar_i32(
        context,
        owned.raw(),
        b"codex_agent_interaction_state_has_failure\0",
    )? == 0
    {
        None
    } else {
        Some(read_failure(
            context,
            child(
                context,
                owned.raw(),
                b"codex_agent_interaction_state_failure\0",
            )?,
        )?)
    };
    owned.close()?;
    Ok(InteractionState::new(pending, resolving, failure))
}

fn approval_raw(
    owner: &Arc<ServiceInner<ffi::Interactions>>,
    value: &PendingApproval,
) -> Result<*mut ffi::PendingApproval, CodexError> {
    let identity = value.binding_identity().ok_or_else(|| {
        CodexError::new(
            Status::InvalidArgument,
            "approval was not emitted by this service",
        )
    })?;
    owner
        .pending
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .iter()
        .find_map(|pending| match pending {
            RetainedPending::Approval {
                identity: candidate,
                handle,
            } if Arc::ptr_eq(identity, candidate) => handle.ptr().ok(),
            _ => None,
        })
        .ok_or_else(|| {
            CodexError::new(
                Status::InvalidArgument,
                "approval identity is not live in this service",
            )
        })
}

fn elicitation_raw(
    owner: &Arc<ServiceInner<ffi::Interactions>>,
    value: &PendingElicitation,
) -> Result<*mut ffi::PendingElicitation, CodexError> {
    let identity = value.binding_identity().ok_or_else(|| {
        CodexError::new(
            Status::InvalidArgument,
            "elicitation was not emitted by this service",
        )
    })?;
    owner
        .pending
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .iter()
        .find_map(|pending| match pending {
            RetainedPending::Elicitation {
                identity: candidate,
                handle,
            } if Arc::ptr_eq(identity, candidate) => handle.ptr().ok(),
            _ => None,
        })
        .ok_or_else(|| {
            CodexError::new(
                Status::InvalidArgument,
                "elicitation identity is not live in this service",
            )
        })
}

fn interaction_approval_operation(
    owner: Arc<ServiceInner<ffi::Interactions>>,
    approval: &PendingApproval,
    decision: ApprovalDecision,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Interactions,
        *mut ffi::PendingApproval,
        i32,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let raw = approval_raw(&owner, approval)?;
    let start: ExactSymbol<Start> = exact_symbol(
        &owner.handle.context,
        b"codex_agent_interactions_resolve_approval\0",
    )?;
    operation(
        owner,
        b"codex_agent_interactions_resolve_approval\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |context, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        context.ptr(),
                        service,
                        raw,
                        decision as i32,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |_, _| Ok(()),
    )
}

fn interaction_elicitation_operation(
    owner: Arc<ServiceInner<ffi::Interactions>>,
    elicitation: &PendingElicitation,
    response: &crate::ElicitationResponse,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Interactions,
        *mut ffi::PendingElicitation,
        *mut ffi::ElicitationResponse,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let raw = elicitation_raw(&owner, elicitation)?;
    let context = owner.handle.context.clone();
    let response = encode_elicitation_response(&context, response)?;
    let response_raw = response.raw();
    let start: ExactSymbol<Start> =
        exact_symbol(&context, b"codex_agent_interactions_resolve_elicitation\0")?;
    let result = operation(
        owner,
        b"codex_agent_interactions_resolve_elicitation\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |current, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(
                        current.ptr(),
                        service,
                        raw,
                        response_raw,
                        callback,
                        user_data,
                        output,
                    )
                }
            })
        },
        |_, _| Ok(()),
    );
    response.close()?;
    result
}

fn interaction_open_url(
    owner: Arc<ServiceInner<ffi::Interactions>>,
    elicitation: &PendingElicitation,
) -> Result<CodexOperation<()>, CodexError> {
    type Start = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Interactions,
        *mut ffi::PendingElicitation,
        ffi::OperationCallback,
        *mut c_void,
        *mut *mut ffi::Operation,
    ) -> i32;
    let raw = elicitation_raw(&owner, elicitation)?;
    let start: ExactSymbol<Start> = exact_symbol(
        &owner.handle.context,
        b"codex_agent_interactions_open_url\0",
    )?;
    operation(
        owner,
        b"codex_agent_interactions_open_url\0",
        // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
        move |context, service, callback, user_data, output| {
            start.invoke(|call| {
                ffi_call! {
                    call(context.ptr(), service, raw, callback, user_data, output)
                }
            })
        },
        |_, _| Ok(()),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;
    use std::future::Future;
    use std::path::{Path, PathBuf};
    use std::sync::OnceLock;
    use std::task::{Context, Poll, Wake, Waker};

    struct ThreadWake(std::thread::Thread);

    impl Wake for ThreadWake {
        fn wake(self: Arc<Self>) {
            self.0.unpark();
        }

        fn wake_by_ref(self: &Arc<Self>) {
            self.0.unpark();
        }
    }

    unsafe extern "C" fn ignored_operation_callback(
        _: *mut ffi::Context,
        _: *mut ffi::Operation,
        _: *mut c_void,
    ) {
    }

    fn block_on<F: Future>(future: F) -> F::Output {
        let waker = Waker::from(Arc::new(ThreadWake(std::thread::current())));
        let mut task_context = Context::from_waker(&waker);
        let mut future = Box::pin(future);
        loop {
            match future.as_mut().poll(&mut task_context) {
                Poll::Ready(value) => return value,
                Poll::Pending => std::thread::park_timeout(std::time::Duration::from_millis(10)),
            }
        }
    }

    fn fixture() -> &'static Path {
        static FIXTURE: OnceLock<PathBuf> = OnceLock::new();
        FIXTURE.get_or_init(|| {
            let output = std::env::temp_dir().join(format!(
                "libcodex_agent_rust_leaf_{}.{}",
                std::process::id(),
                if cfg!(target_os = "macos") {
                    "dylib"
                } else {
                    "so"
                }
            ));
            let source = Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/mock_leaf_codex_agent.c");
            let mut command = std::process::Command::new("cc");
            command.args([
                "-std=gnu11",
                "-fPIC",
                "-pthread",
                "-Wall",
                "-Wextra",
                "-Werror",
            ]);
            command.arg(if cfg!(target_os = "macos") {
                "-dynamiclib"
            } else {
                "-shared"
            });
            let result = command
                .arg(source)
                .arg("-o")
                .arg(&output)
                .output()
                .expect("compile leaf fixture");
            assert!(
                result.status.success(),
                "leaf fixture failed:\n{}",
                String::from_utf8_lossy(&result.stderr)
            );
            output
        })
    }

    fn context() -> Arc<ContextInner> {
        let native = crate::CodexNativeLibrary::load(fixture()).expect("load leaf fixture");
        ContextInner::create(native.inner.clone()).expect("create leaf context")
    }

    fn raw_service<T>(context: &Arc<ContextInner>, kind: i32) -> *mut T {
        type Factory = unsafe extern "C" fn(*mut ffi::Context, i32, *mut *mut c_void) -> i32;
        let factory: Factory =
            symbol(context, b"codex_agent_test_leaf_service\0").expect("load leaf factory");
        let mut raw = std::ptr::null_mut();
        assert_eq!(
            // SAFETY: the typed function pointer and all handles and output slots follow its exact C declaration.
            unsafe { factory(context.ptr(), kind, &mut raw) },
            ffi::STATUS_OK
        );
        raw.cast()
    }

    macro_rules! leaf_service_factory {
        ($function:ident, $service:ident, $kind:literal) => {
            fn $function(context: &Arc<ContextInner>) -> $service {
                $service::from_raw(context.clone(), raw_service(context, $kind))
            }
        };
    }

    leaf_service_factory!(authentication, CodexAuthentication, 0);
    leaf_service_factory!(connectors, CodexConnectors, 1);
    leaf_service_factory!(hooks, CodexHooks, 2);
    leaf_service_factory!(authorization, CodexIntegrationAuthorization, 3);
    leaf_service_factory!(interactions, CodexInteractions, 4);
    leaf_service_factory!(mcp_servers, CodexMcpServers, 5);
    leaf_service_factory!(models, CodexModels, 6);
    leaf_service_factory!(plugins, CodexPlugins, 7);
    leaf_service_factory!(skills, CodexSkills, 8);

    fn model() -> Model {
        Model::new(
            "model",
            "Model",
            "",
            vec!["medium".into()],
            "medium",
            true,
            Vec::new(),
            None,
        )
    }

    fn plugin() -> PluginReference {
        PluginReference::new("plugin-id", "plugin", "market", None, None)
    }

    fn connector() -> Connector {
        Connector::new("connector", "Connector", "", None, true, true, Vec::new())
    }

    fn mcp_configuration() -> McpServerConfiguration {
        McpServerConfiguration {
            name: "server".into(),
            transport: crate::McpTransport::Stdio(
                crate::McpStdioTransport::new("tool", Vec::new(), None, None, Vec::new()).unwrap(),
            ),
            authentication: None,
            environment_id: "local".into(),
            is_enabled: true,
            is_required: false,
            supports_parallel_tool_calls: false,
            omit_tools_from: None,
            startup_timeout_seconds: None,
            tool_timeout_seconds: None,
            default_tool_approval: None,
            enabled_tools: None,
            disabled_tools: None,
            scopes: None,
            oauth: None,
            oauth_resource: None,
            tools: std::collections::BTreeMap::new(),
        }
    }

    fn current_and_updates<T>(state: &CodexObservableState<T>) -> (T, Vec<T>)
    where
        T: std::fmt::Debug + PartialEq,
    {
        let current = state.current().expect("current state");
        let mut updates = state.subscribe().expect("subscribe state");
        let mut values = Vec::new();
        while let Some(update) = block_on(updates.next()) {
            values.push(update.expect("valid state update"));
        }
        assert!(
            values.len() >= 3,
            "fixture emits initial, later, and terminal values"
        );
        assert_eq!(
            values.first(),
            Some(&current),
            "subscription begins at current value"
        );
        assert!(
            values.iter().skip(1).any(|value| value != &current),
            "state stream must contain a genuinely later distinct update"
        );
        (current, values)
    }

    fn set_leaf_fixture(context: &Arc<ContextInner>, name: &'static [u8], value: i32) {
        type Set = unsafe extern "C" fn(i32);
        let set: Set = symbol(context, name).expect("load exact leaf-fixture control");
        // SAFETY: the fixture setter accepts exactly one integer mode and borrows no memory.
        unsafe { set(value) };
    }

    fn leaf_release_count(context: &Arc<ContextInner>, kind: i32) -> i32 {
        type Get = unsafe extern "C" fn(i32) -> i32;
        let get: Get = symbol(context, b"codex_agent_test_leaf_release_count\0")
            .expect("load leaf release counter");
        // SAFETY: the fixture counter accepts exactly one validated service-kind integer.
        unsafe { get(kind) }
    }

    fn subscription_destroy_count(context: &Arc<ContextInner>) -> i32 {
        type Get = unsafe extern "C" fn() -> i32;
        let get: Get = symbol(context, b"codex_agent_test_subscription_destroy_count\0")
            .expect("load subscription destroy counter");
        // SAFETY: the fixture counter has no arguments and returns one integer snapshot.
        unsafe { get() }
    }

    fn release_log(context: &Arc<ContextInner>) -> Vec<u8> {
        type Copy = unsafe extern "C" fn(*mut u8, usize, *mut usize) -> i32;
        let copy: Copy = symbol(context, b"codex_agent_test_release_log_copy\0")
            .expect("load release-log copier");
        let mut required = 0;
        let mut bytes = Vec::new();
        loop {
            let buffer = if bytes.is_empty() {
                std::ptr::null_mut()
            } else {
                bytes.as_mut_ptr()
            };
            // SAFETY: buffer is null for zero capacity or writable for bytes.len().
            let status = unsafe { copy(buffer, bytes.len(), &mut required) };
            match status {
                ffi::STATUS_OK => {
                    bytes.truncate(required);
                    return bytes;
                }
                ffi::STATUS_BUFFER_TOO_SMALL => {
                    assert!(required > bytes.len(), "release-log size must grow");
                    bytes.resize(required, 0);
                }
                _ => panic!("unexpected release-log copy status: {status}"),
            }
        }
    }

    fn wait_for_count(mut count: impl FnMut() -> i32, expected: i32, description: &str) {
        for _ in 0..2_000 {
            if count() >= expected {
                return;
            }
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        panic!(
            "timed out waiting for {description}: expected {expected}, got {}",
            count()
        );
    }

    fn operation_after_parent_drop<S, T>(
        context: &Arc<ContextInner>,
        kind: i32,
        service: S,
        start: impl FnOnce(&S) -> Result<CodexOperation<T>, CodexError>,
    ) -> Result<T, CodexError> {
        let before = leaf_release_count(context, kind);
        let operation = start(&service).expect("start owned leaf operation");
        drop(service);
        assert_eq!(
            leaf_release_count(context, kind),
            before,
            "operation must retain its service parent"
        );
        let result = block_on(operation);
        wait_for_count(
            || leaf_release_count(context, kind),
            before + 1,
            "operation-owned service release",
        );
        result
    }

    fn assert_invalid_start<T>(result: Result<CodexOperation<T>, CodexError>, description: &str) {
        match result {
            Err(error) => assert_eq!(error.status, Status::InvalidArgument, "{description}"),
            Ok(_) => panic!("{description}: wrong value unexpectedly started an operation"),
        }
    }

    fn state_behavior<S, T>(
        context: &Arc<ContextInner>,
        kind: i32,
        service: S,
        state: CodexObservableState<T>,
    ) -> (T, Vec<T>)
    where
        T: std::fmt::Debug + PartialEq,
    {
        let release_before = leaf_release_count(context, kind);
        let subscriptions_before = subscription_destroy_count(context);
        drop(service);
        assert_eq!(
            leaf_release_count(context, kind),
            release_before,
            "observable state must retain its service parent"
        );
        let result = current_and_updates(&state);
        set_leaf_fixture(context, b"codex_agent_test_leaf_set_terminal\0", 0);
        let stream = state.subscribe().expect("subscribe cancellable state");
        drop(stream);
        set_leaf_fixture(context, b"codex_agent_test_leaf_set_terminal\0", 1);
        wait_for_count(
            || subscription_destroy_count(context),
            subscriptions_before + 2,
            "terminal and cancelled subscription quiescence",
        );
        drop(state);
        wait_for_count(
            || leaf_release_count(context, kind),
            release_before + 1,
            "observable-owned service release",
        );
        result
    }

    fn cancel_operation<S, T>(
        context: &Arc<ContextInner>,
        kind: i32,
        service: S,
        start: impl FnOnce(&S) -> Result<CodexOperation<T>, CodexError>,
    ) {
        let before = leaf_release_count(context, kind);
        set_leaf_fixture(context, b"codex_agent_test_leaf_set_completion_mode\0", 0);
        let operation = start(&service).expect("start cancellable leaf operation");
        drop(service);
        assert_eq!(
            leaf_release_count(context, kind),
            before,
            "cancelled operation must retain its service parent"
        );
        operation
            .cancel()
            .expect("request leaf-operation cancellation");
        match block_on(operation) {
            Err(error) => assert_eq!(error.status, Status::Cancelled),
            Ok(_) => panic!("cancelled leaf operation unexpectedly succeeded"),
        }
        wait_for_count(
            || leaf_release_count(context, kind),
            before + 1,
            "cancelled operation-owned service release",
        );
        set_leaf_fixture(context, b"codex_agent_test_leaf_set_completion_mode\0", 1);
    }

    fn availability_behavior<S: Clone>(
        context: &Arc<ContextInner>,
        kind: i32,
        service: S,
        available: impl FnOnce(&S) -> Result<bool, CodexError>,
    ) {
        let before = leaf_release_count(context, kind);
        let alias = service.clone();
        drop(service);
        assert_eq!(
            leaf_release_count(context, kind),
            before,
            "first alias disposal must retain the service"
        );
        assert!(available(&alias).expect("read service availability"));
        drop(alias);
        wait_for_count(
            || leaf_release_count(context, kind),
            before + 1,
            "exactly-once aliased service release",
        );
        assert_eq!(
            leaf_release_count(context, kind),
            before + 1,
            "repeated alias disposal must release the native service exactly once"
        );
    }

    fn interaction_approval_at(
        context: &Arc<ContextInner>,
        index: usize,
    ) -> (CodexInteractions, PendingApproval) {
        let service = interactions(context);
        let state = service.approvals().expect("create approval state");
        let mut values = state.current().expect("read approval identity");
        drop(state);
        assert_eq!(values.len(), 3);
        (service, values.remove(index))
    }

    fn interaction_approval(context: &Arc<ContextInner>) -> (CodexInteractions, PendingApproval) {
        interaction_approval_at(context, 0)
    }

    fn interaction_elicitation_at(
        context: &Arc<ContextInner>,
        index: usize,
    ) -> (CodexInteractions, PendingElicitation) {
        let service = interactions(context);
        let state = service.elicitations().expect("create elicitation state");
        let mut values = state.current().expect("read elicitation identity");
        drop(state);
        assert_eq!(values.len(), 3);
        (service, values.remove(index))
    }

    fn interaction_elicitation(
        context: &Arc<ContextInner>,
    ) -> (CodexInteractions, PendingElicitation) {
        interaction_elicitation_at(context, 0)
    }

    fn exact_claim_calls(public_symbol: &str, test_id: &str) -> BTreeSet<String> {
        let claims = std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("parity/capability-claims.tsv"),
        )
        .expect("read exact Rust capability claims");
        let row = claims
            .lines()
            .skip(1)
            .map(|line| line.split('\t').collect::<Vec<_>>())
            .find(|row| {
                row.get(2) == Some(&test_id)
                    && row.get(1).is_some_and(|symbols| {
                        symbols.split(',').any(|symbol| symbol == public_symbol)
                    })
            })
            .expect("public leaf-service claim exists");
        row[3]
            .split(',')
            .filter_map(|item| item.strip_prefix("c-header:"))
            .map(str::to_owned)
            .collect()
    }

    fn leaf_reference_universe() -> BTreeSet<String> {
        std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("parity/capability-claims.tsv"),
        )
        .expect("read exact Rust capability claims")
        .lines()
        .skip(1)
        .map(|line| line.split('\t').collect::<Vec<_>>())
        .filter(|row| row.get(2).is_some_and(|id| id.starts_with("rust.service:")))
        .flat_map(|row| {
            row[3]
                .split(',')
                .filter_map(|item| item.strip_prefix("c-header:"))
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .collect()
    }

    fn validate_claim_invocations(
        expected: &BTreeSet<String>,
        actual: &BTreeSet<String>,
    ) -> Result<(), String> {
        let universe = leaf_reference_universe();
        let actual = actual
            .intersection(&universe)
            .cloned()
            .collect::<BTreeSet<_>>();
        if &actual == expected {
            Ok(())
        } else {
            Err(format!(
                "missing={:?}; wrong={:?}",
                expected.difference(&actual).collect::<Vec<_>>(),
                actual.difference(expected).collect::<Vec<_>>()
            ))
        }
    }

    fn case<R>(
        executed: &mut BTreeSet<String>,
        public_symbol: &str,
        test_id: &str,
        action: impl FnOnce() -> R,
    ) -> R {
        assert!(
            executed.insert(test_id.to_owned()),
            "duplicate service case"
        );
        crate::ffi::test_clear_calls();
        let result = action();
        let actual = crate::ffi::test_calls();
        let expected = exact_claim_calls(public_symbol, test_id);
        validate_claim_invocations(&expected, &actual).unwrap_or_else(|error| {
            panic!("{test_id} exact production invocation mismatch: {error}")
        });
        result
    }

    fn conversation_reference_universe() -> BTreeSet<String> {
        std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("parity/capability-claims.tsv"),
        )
        .expect("read exact Rust capability claims")
        .lines()
        .skip(1)
        .map(|line| line.split('\t').collect::<Vec<_>>())
        .filter(|row| {
            row.get(2)
                .is_some_and(|id| id.starts_with("rust.conversation:"))
        })
        .flat_map(|row| {
            row[3]
                .split(',')
                .filter_map(|item| item.strip_prefix("c-header:"))
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .collect()
    }

    fn validate_conversation_invocations(
        expected: &BTreeSet<String>,
        actual: &BTreeSet<String>,
    ) -> Result<(), String> {
        let universe = conversation_reference_universe();
        let mut actual = actual
            .intersection(&universe)
            .cloned()
            .collect::<BTreeSet<_>>();
        if !expected.contains("codex_agent_operation_result") {
            actual.remove("codex_agent_operation_result");
        }
        if &actual == expected {
            Ok(())
        } else {
            Err(format!(
                "missing={:?}; wrong={:?}",
                expected.difference(&actual).collect::<Vec<_>>(),
                actual.difference(expected).collect::<Vec<_>>()
            ))
        }
    }

    fn conversation_case<R>(
        executed: &mut BTreeSet<String>,
        public_symbol: &str,
        test_id: &str,
        action: impl FnOnce() -> R,
    ) -> R {
        assert!(
            executed.insert(test_id.to_owned()),
            "duplicate conversation case"
        );
        crate::ffi::test_clear_calls();
        let result = action();
        let actual = crate::ffi::test_calls();
        let expected = exact_claim_calls(public_symbol, test_id);
        validate_conversation_invocations(&expected, &actual).unwrap_or_else(|error| {
            panic!("{test_id} exact conversation invocation mismatch: {error}")
        });
        result
    }

    fn agent_reference_universe() -> BTreeSet<String> {
        std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("parity/capability-claims.tsv"),
        )
        .expect("read exact Rust capability claims")
        .lines()
        .skip(1)
        .map(|line| line.split('\t').collect::<Vec<_>>())
        .filter(|row| row.get(2).is_some_and(|id| id.starts_with("rust.agent:")))
        .flat_map(|row| {
            row[3]
                .split(',')
                .filter_map(|item| item.strip_prefix("c-header:"))
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .collect()
    }

    fn validate_agent_invocations(
        expected: &BTreeSet<String>,
        actual: &BTreeSet<String>,
    ) -> Result<(), String> {
        let universe = agent_reference_universe();
        let actual = actual
            .intersection(&universe)
            .cloned()
            .collect::<BTreeSet<_>>();
        if &actual == expected {
            Ok(())
        } else {
            Err(format!(
                "missing={:?}; wrong={:?}",
                expected.difference(&actual).collect::<Vec<_>>(),
                actual.difference(expected).collect::<Vec<_>>()
            ))
        }
    }

    fn agent_case<R>(
        executed: &mut BTreeSet<String>,
        public_symbol: &str,
        test_id: &str,
        action: impl FnOnce() -> R,
    ) -> R {
        assert!(executed.insert(test_id.to_owned()), "duplicate Agent case");
        crate::ffi::test_clear_calls();
        let result = action();
        let actual = crate::ffi::test_calls();
        let expected = exact_claim_calls(public_symbol, test_id);
        validate_agent_invocations(&expected, &actual)
            .unwrap_or_else(|error| panic!("{test_id} exact Agent invocation mismatch: {error}"));
        result
    }

    fn host_reference_universe() -> BTreeSet<String> {
        std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("parity/capability-claims.tsv"),
        )
        .expect("read exact Rust capability claims")
        .lines()
        .skip(1)
        .map(|line| line.split('\t').collect::<Vec<_>>())
        .filter(|row| row.get(2).is_some_and(|id| id.starts_with("rust.host:")))
        .flat_map(|row| {
            row[3]
                .split(',')
                .filter_map(|item| item.strip_prefix("c-header:"))
                .filter(|item| item.starts_with("codex_agent_") && !item.ends_with("_t"))
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .collect()
    }

    fn validate_host_invocations(
        expected: &BTreeSet<String>,
        actual: &BTreeSet<String>,
    ) -> Result<(), String> {
        let universe = host_reference_universe();
        let mut actual = actual
            .intersection(&universe)
            .cloned()
            .collect::<BTreeSet<_>>();
        for prerequisite in [
            "codex_agent_host_state_get",
            "codex_agent_host_state_kind",
            "codex_agent_host_state_agent",
            "codex_agent_operation_result",
        ] {
            if !expected.contains(prerequisite) {
                actual.remove(prerequisite);
            }
        }
        if &actual == expected {
            Ok(())
        } else {
            Err(format!(
                "missing={:?}; wrong={:?}",
                expected.difference(&actual).collect::<Vec<_>>(),
                actual.difference(expected).collect::<Vec<_>>()
            ))
        }
    }

    fn host_case<R>(
        executed: &mut BTreeSet<String>,
        public_symbol: &str,
        test_id: &str,
        action: impl FnOnce() -> R,
    ) -> R {
        assert!(executed.insert(test_id.to_owned()), "duplicate Host case");
        crate::ffi::test_clear_calls();
        let result = action();
        let actual = crate::ffi::test_calls();
        let expected = exact_claim_calls(public_symbol, test_id);
        let expected = expected
            .into_iter()
            .filter(|reference| reference.starts_with("codex_agent_") && !reference.ends_with("_t"))
            .collect();
        validate_host_invocations(&expected, &actual)
            .unwrap_or_else(|error| panic!("{test_id} exact Host invocation mismatch: {error}"));
        result
    }

    fn exercise_host_operation(
        context: &Arc<ContextInner>,
        owner: &Arc<crate::HostInner>,
        start: impl Fn() -> Result<CodexOperation<()>, CodexError>,
    ) {
        let baseline = Arc::strong_count(owner);
        let await_owner_release = || {
            for _ in 0..2_000 {
                if Arc::strong_count(owner) == baseline {
                    return;
                }
                std::thread::sleep(std::time::Duration::from_millis(1));
            }
            panic!(
                "Host operation did not release its parent: expected {baseline}, got {}",
                Arc::strong_count(owner)
            );
        };
        set_leaf_fixture(
            context,
            b"codex_agent_test_set_host_operation_result\0",
            ffi::STATUS_OPERATION_FAILED,
        );
        set_leaf_fixture(
            context,
            b"codex_agent_test_set_host_operation_completion_mode\0",
            1,
        );
        let before = Arc::strong_count(owner);
        let failed = start().expect("start exact failing Host operation");
        assert!(Arc::strong_count(owner) > before);
        let failure = block_on(failed).expect_err("Host operation failure");
        assert_eq!(failure.status, Status::OperationFailed);
        let failure = failure.failure.expect("structured Host operation failure");
        assert_eq!(failure.code, "mock.failure");
        assert_eq!(failure.message, "structured failure");
        assert!(failure.recoverable);
        await_owner_release();

        set_leaf_fixture(
            context,
            b"codex_agent_test_set_host_operation_result\0",
            ffi::STATUS_OK,
        );
        set_leaf_fixture(
            context,
            b"codex_agent_test_set_host_operation_completion_mode\0",
            0,
        );
        let before = Arc::strong_count(owner);
        let cancelled = start().expect("start exact cancellable Host operation");
        assert!(Arc::strong_count(owner) > before);
        cancelled.cancel().expect("cancel exact Host operation");
        assert_eq!(block_on(cancelled).unwrap_err().status, Status::Cancelled);
        await_owner_release();

        set_leaf_fixture(
            context,
            b"codex_agent_test_set_host_operation_completion_mode\0",
            1,
        );
        let before = Arc::strong_count(owner);
        let succeeded = start().expect("start exact successful Host operation");
        assert!(Arc::strong_count(owner) > before);
        block_on(succeeded).expect("complete exact Host operation");
        await_owner_release();
    }

    fn finish_retained<T, O>(
        owner: &Arc<O>,
        before: usize,
        operation: CodexOperation<T>,
    ) -> Result<T, CodexError> {
        assert!(
            Arc::strong_count(owner) > before,
            "operation must retain its exact conversation parent"
        );
        block_on(operation)
    }

    fn stable_strong_count<T>(owner: &Arc<T>) -> usize {
        let mut last = Arc::strong_count(owner);
        let mut stable = 0;
        for _ in 0..2_000 {
            std::thread::sleep(std::time::Duration::from_millis(1));
            let current = Arc::strong_count(owner);
            if current == last {
                stable += 1;
                if stable == 10 {
                    return current;
                }
            } else {
                last = current;
                stable = 0;
            }
        }
        last
    }

    fn set_conversation_fixture(context: &Arc<ContextInner>, name: &'static [u8], value: i32) {
        set_leaf_fixture(context, name, value);
    }

    fn assert_conversation_state<T>(
        context: &Arc<ContextInner>,
        state: CodexObservableState<T>,
        current: impl Fn(&T) -> bool,
        subsequent: impl Fn(&T) -> bool,
    ) where
        T: std::fmt::Debug,
    {
        assert!(current(
            &state.current().expect("conversation current value")
        ));
        let mut stream = state.subscribe().expect("conversation state stream");
        let first = block_on(stream.next())
            .expect("current event")
            .expect("valid current event");
        let second = block_on(stream.next())
            .expect("subsequent event")
            .expect("valid subsequent event");
        assert!(current(&first), "stream starts at exact current value");
        assert!(
            subsequent(&second),
            "stream emits exact distinct subsequent value"
        );
        assert!(
            block_on(stream.next()).is_none(),
            "stream delivers terminal event"
        );
        drop(stream);

        let before = subscription_destroy_count(context);
        set_conversation_fixture(context, b"codex_agent_test_conversation_terminal\0", 0);
        let cancelled = state.subscribe().expect("cancellable conversation state");
        drop(cancelled);
        wait_for_count(
            || subscription_destroy_count(context),
            before + 1,
            "cancelled conversation subscription cleanup",
        );
        type Publish = unsafe extern "C" fn(*mut ffi::Context) -> i32;
        let publish: Publish = symbol(
            context,
            b"codex_agent_test_conversation_publish_after_cancel\0",
        )
        .expect("load post-cancel publisher");
        let mut status = ffi::STATUS_OK;
        for _ in 0..2_000 {
            // SAFETY: the test context remains alive for the duration of this exact test hook call.
            status = unsafe { publish(context.ptr()) };
            if status == ffi::STATUS_NOT_READY {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        assert_eq!(
            status,
            ffi::STATUS_NOT_READY,
            "cancelled state must remain silent"
        );
        set_conversation_fixture(context, b"codex_agent_test_conversation_terminal\0", 1);
    }

    #[test]
    fn all_42_leaf_capabilities_execute_through_the_production_wrapper() {
        let _call_session = crate::ffi::test_call_session();
        let context = context();
        let mut executed = BTreeSet::new();

        crate::ffi::test_clear_calls();
        let _: ServiceOperation<ffi::Authentication> =
            symbol(&context, b"codex_agent_authentication_cancel\0")
                .expect("resolve exact negative lookup");
        assert!(
            crate::ffi::test_calls().is_empty(),
            "successful symbol lookup is not invocation evidence"
        );
        let cancel_calls = exact_claim_calls(
            "codex_agent::CodexAuthentication::cancel",
            "rust.service:001",
        );
        let sign_out_calls = exact_claim_calls(
            "codex_agent::CodexAuthentication::sign_out",
            "rust.service:002",
        );
        assert!(
            validate_claim_invocations(&cancel_calls, &sign_out_calls).is_err(),
            "wrong-method invocation evidence must fail closed"
        );
        let wrong: ExactSymbol<ServiceOperation<ffi::Authentication>> =
            exact_symbol(&context, b"codex_agent_authentication_cancel\0")
                .expect("load exact wrong-invocation negative");
        crate::ffi::test_clear_calls();
        let mut output = std::ptr::null_mut();
        assert_ne!(
            wrong.invoke(|call| ffi_call! {
                call(
                    context.ptr(),
                    std::ptr::null_mut(),
                    ignored_operation_callback,
                    std::ptr::null_mut(),
                    &mut output,
                )
            }),
            ffi::STATUS_OK,
            "wrong-invocation negative must fail at the native boundary"
        );
        assert!(
            validate_claim_invocations(&sign_out_calls, &crate::ffi::test_calls()).is_err(),
            "an actually invoked wrong function must fail exact method evidence"
        );
        let stale = BTreeSet::from(["codex_agent_removed_stale_trace".to_owned()]);
        assert!(
            validate_claim_invocations(&cancel_calls, &stale).is_err(),
            "stale invocation trace must fail closed"
        );
        case(
            &mut executed,
            "codex_agent::CodexAuthentication::authenticate",
            "rust.service:000",
            || {
                operation_after_parent_drop(&context, 0, authentication(&context), |service| {
                    service.authenticate(&AuthenticationMethod::ApiKey(
                        crate::ApiKeyAuthentication::new("secret").unwrap(),
                    ))
                })
                .unwrap();
                operation_after_parent_drop(&context, 0, authentication(&context), |service| {
                    service.authenticate(&AuthenticationMethod::ChatGptBrowser(
                        crate::ChatGptBrowserAuthentication::INSTANCE,
                    ))
                })
                .unwrap();
                operation_after_parent_drop(&context, 0, authentication(&context), |service| {
                    service.authenticate(&AuthenticationMethod::ChatGptDeviceCode(
                        crate::ChatGptDeviceCodeAuthentication::INSTANCE,
                    ))
                })
                .unwrap();
                assert_invalid_start(
                    authentication(&context).authenticate(&AuthenticationMethod::ApiKey(
                        crate::ApiKeyAuthentication::new("wrong-secret").unwrap(),
                    )),
                    "API-key payload must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexAuthentication::cancel",
            "rust.service:001",
            || {
                operation_after_parent_drop(&context, 0, authentication(&context), |service| {
                    service.cancel()
                })
                .unwrap()
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexAuthentication::sign_out",
            "rust.service:002",
            || {
                operation_after_parent_drop(&context, 0, authentication(&context), |service| {
                    service.sign_out()
                })
                .unwrap()
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexAuthentication::is_authenticated",
            "rust.service:003",
            || {
                let service = authentication(&context);
                let state = service.is_authenticated().unwrap();
                assert_eq!(
                    state_behavior(&context, 0, service, state),
                    (true, vec![true, false, true])
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexAuthentication::is_authenticating",
            "rust.service:004",
            || {
                let service = authentication(&context);
                let state = service.is_authenticating().unwrap();
                assert_eq!(
                    state_behavior(&context, 0, service, state),
                    (true, vec![true, false, true])
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexAuthentication::state",
            "rust.service:005",
            || {
                let service = authentication(&context);
                let state = service.state().unwrap();
                let _ = state_behavior(&context, 0, service, state);
            },
        );

        case(
            &mut executed,
            "codex_agent::CodexConnectors::list",
            "rust.service:006",
            || {
                let values =
                    operation_after_parent_drop(&context, 1, connectors(&context), |service| {
                        service.list(true)
                    })
                    .unwrap();
                assert_eq!(
                    values
                        .iter()
                        .map(|value| value.id.as_str())
                        .collect::<Vec<_>>(),
                    ["connector-a", "connector-b", "connector-a"]
                );
                assert_invalid_start(
                    connectors(&context).list(false),
                    "connector force-refresh flag must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexConnectors::is_available",
            "rust.service:007",
            || {
                availability_behavior(&context, 1, connectors(&context), |service| {
                    service.is_available()
                })
            },
        );

        let hook = case(
            &mut executed,
            "codex_agent::CodexHooks::install",
            "rust.service:008",
            || {
                let installed =
                    operation_after_parent_drop(&context, 2, hooks(&context), |service| {
                        service.install("hooks", InstallationScope::User)
                    })
                    .unwrap();
                assert_invalid_start(
                    hooks(&context).install("wrong-hooks", InstallationScope::User),
                    "hook path must be copied exactly",
                );
                assert_invalid_start(
                    hooks(&context).install("hooks", InstallationScope::Workspace),
                    "hook scope must be copied exactly",
                );
                installed
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexHooks::list",
            "rust.service:009",
            || {
                assert!(
                    operation_after_parent_drop(&context, 2, hooks(&context), |service| {
                        service.list()
                    })
                    .unwrap()
                    .hooks
                    .is_empty()
                )
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexHooks::trust",
            "rust.service:010",
            || {
                operation_after_parent_drop(&context, 2, hooks(&context), |service| {
                    service.trust(&hook)
                })
                .unwrap();
                let mut wrong = hook.clone();
                wrong.key = "wrong-hook".into();
                assert_invalid_start(
                    hooks(&context).trust(&wrong),
                    "trusted hook fields must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexHooks::uninstall",
            "rust.service:011",
            || {
                operation_after_parent_drop(&context, 2, hooks(&context), |service| {
                    service.uninstall(&hook)
                })
                .unwrap();
                let mut wrong = hook.clone();
                wrong.source_path = "wrong-hooks".into();
                assert_invalid_start(
                    hooks(&context).uninstall(&wrong),
                    "uninstalled hook fields must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexHooks::is_available",
            "rust.service:012",
            || {
                availability_behavior(&context, 2, hooks(&context), |service| {
                    service.is_available()
                })
            },
        );

        case(
            &mut executed,
            "codex_agent::CodexIntegrationAuthorization::authorize",
            "rust.service:013",
            || {
                operation_after_parent_drop(&context, 3, authorization(&context), |service| {
                    service.authorize(&Integration::Connector(crate::ConnectorIntegration::new(
                        connector(),
                    )))
                })
                .unwrap();
                let server = McpServer::new(
                    "server",
                    "Server",
                    crate::McpAuthStatus::NotLoggedIn,
                    None,
                    crate::ResourceOrigin::User,
                    true,
                );
                operation_after_parent_drop(&context, 3, authorization(&context), |service| {
                    service.authorize(&Integration::McpServer(Box::new(
                        crate::McpServerIntegration::new(server),
                    )))
                })
                .unwrap();
                assert_invalid_start(
                    authorization(&context).authorize(&Integration::Connector(
                        crate::ConnectorIntegration::new(Connector::new(
                            "wrong-connector",
                            "Connector",
                            "",
                            None,
                            true,
                            true,
                            Vec::new(),
                        )),
                    )),
                    "integration variant payload must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexIntegrationAuthorization::cancel",
            "rust.service:014",
            || {
                operation_after_parent_drop(&context, 3, authorization(&context), |service| {
                    service.cancel()
                })
                .unwrap()
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexIntegrationAuthorization::active",
            "rust.service:015",
            || {
                let service = authorization(&context);
                let state = service.active().unwrap();
                let (current, updates) = state_behavior(&context, 3, service, state);
                assert!(
                    current.is_none(),
                    "active authorization covers nullable None"
                );
                assert!(updates[0].is_none());
                assert!(matches!(updates[1], Some(Integration::Connector(_))));
                assert!(matches!(updates[2], Some(Integration::McpServer(_))));
                assert!(updates[3].is_none());
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexIntegrationAuthorization::is_authorizing",
            "rust.service:016",
            || {
                let service = authorization(&context);
                let state = service.is_authorizing().unwrap();
                assert_eq!(
                    state_behavior(&context, 3, service, state),
                    (true, vec![true, false, true])
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexIntegrationAuthorization::state",
            "rust.service:017",
            || {
                let service = authorization(&context);
                let state = service.state().unwrap();
                let _ = state_behavior(&context, 3, service, state);
            },
        );

        let (approvals, approval_updates) = case(
            &mut executed,
            "codex_agent::CodexInteractions::approvals",
            "rust.service:021",
            || {
                let service = interactions(&context);
                let state = service.approvals().unwrap();
                state_behavior(&context, 4, service, state)
            },
        );
        let (elicitations, elicitation_updates) = case(
            &mut executed,
            "codex_agent::CodexInteractions::elicitations",
            "rust.service:022",
            || {
                let service = interactions(&context);
                let state = service.elicitations().unwrap();
                state_behavior(&context, 4, service, state)
            },
        );
        assert_eq!(
            approvals
                .iter()
                .map(|value| value.request_id.as_str())
                .collect::<Vec<_>>(),
            ["approval-a", "approval-b", "approval-a"]
        );
        assert_eq!(
            elicitations
                .iter()
                .map(|value| value.elicitation.request_id.as_str())
                .collect::<Vec<_>>(),
            ["elicitation-a", "elicitation-b", "elicitation-a"]
        );
        assert_eq!(
            approval_updates.iter().map(Vec::len).collect::<Vec<_>>(),
            [3, 1, 2]
        );
        assert_eq!(
            elicitation_updates.iter().map(Vec::len).collect::<Vec<_>>(),
            [3, 1, 2]
        );
        assert!(approvals[0].binding_identity().is_some());
        assert!(elicitations[0].binding_identity().is_some());

        let (open_cancel_service, open_cancel_value) = interaction_elicitation(&context);
        let (open_success_service, open_success_value) = interaction_elicitation(&context);
        let (open_failure_service, open_failure_value) = interaction_elicitation(&context);
        let (open_wrong_native_service, open_wrong_native_value) =
            interaction_elicitation_at(&context, 1);
        let open_invalid_service = interactions(&context);
        let open_invalid_value = PendingElicitation::new(open_failure_value.elicitation.clone());
        case(
            &mut executed,
            "codex_agent::CodexInteractions::open_url",
            "rust.service:018",
            || {
                cancel_operation(&context, 4, open_cancel_service, |service| {
                    service.open_url(&open_cancel_value)
                });
                operation_after_parent_drop(&context, 4, open_success_service, |service| {
                    service.open_url(&open_success_value)
                })
                .unwrap();
                set_leaf_fixture(&context, b"codex_agent_test_leaf_set_result\0", 14);
                let failure =
                    operation_after_parent_drop(&context, 4, open_failure_service, |service| {
                        service.open_url(&open_failure_value)
                    })
                    .expect_err("fixture open-URL operation must fail");
                assert_eq!(failure.status, Status::OperationFailed);
                assert_eq!(
                    failure.failure.expect("structured failure").code,
                    "mock.failure"
                );
                set_leaf_fixture(&context, b"codex_agent_test_leaf_set_result\0", 0);
                assert!(matches!(
                    open_invalid_service.open_url(&open_invalid_value),
                    Err(CodexError {
                        status: Status::InvalidArgument,
                        ..
                    })
                ));
                assert_invalid_start(
                    open_wrong_native_service.open_url(&open_wrong_native_value),
                    "open-url native identity payload must be passed unchanged",
                );
            },
        );

        let (approval_cancel_service, approval_cancel_value) = interaction_approval(&context);
        let (approval_success_service, approval_success_value) = interaction_approval(&context);
        let (approval_wrong_native_service, approval_wrong_native_value) =
            interaction_approval_at(&context, 1);
        let (approval_wrong_decision_service, approval_wrong_decision_value) =
            interaction_approval(&context);
        let approval_invalid_service = interactions(&context);
        case(
            &mut executed,
            "codex_agent::CodexInteractions::resolve_approval",
            "rust.service:019",
            || {
                cancel_operation(&context, 4, approval_cancel_service, |service| {
                    service.resolve_approval(&approval_cancel_value, ApprovalDecision::Accept)
                });
                operation_after_parent_drop(&context, 4, approval_success_service, |service| {
                    service.resolve_approval(&approval_success_value, ApprovalDecision::Accept)
                })
                .unwrap();
                assert!(matches!(
                    approval_invalid_service.resolve_approval(
                        &PendingApproval::new(
                            "approval-1",
                            crate::ConversationId::new("conversation-1").unwrap(),
                            "Approve",
                            "details",
                        ),
                        ApprovalDecision::Accept,
                    ),
                    Err(CodexError {
                        status: Status::InvalidArgument,
                        ..
                    })
                ));
                assert_invalid_start(
                    approval_wrong_native_service
                        .resolve_approval(&approval_wrong_native_value, ApprovalDecision::Accept),
                    "approval native identity payload must be passed unchanged",
                );
                assert_invalid_start(
                    approval_wrong_decision_service.resolve_approval(
                        &approval_wrong_decision_value,
                        ApprovalDecision::Decline,
                    ),
                    "approval decision must be copied exactly",
                );
            },
        );
        let mut response_content = std::collections::BTreeMap::new();
        response_content.insert(
            "answer".to_owned(),
            crate::FormValue::Text(crate::FormText::new("yes")),
        );
        let response =
            crate::ElicitationResponse::new(crate::ElicitationAction::Accept, response_content);
        let mut wrong_action_response = response.clone();
        wrong_action_response.action = crate::ElicitationAction::Decline;
        let wrong_content_response = crate::ElicitationResponse::new(
            crate::ElicitationAction::Accept,
            std::collections::BTreeMap::new(),
        );
        let (elicitation_cancel_service, elicitation_cancel_value) =
            interaction_elicitation(&context);
        let (elicitation_success_service, elicitation_success_value) =
            interaction_elicitation(&context);
        let (elicitation_wrong_native_service, elicitation_wrong_native_value) =
            interaction_elicitation_at(&context, 1);
        let (elicitation_wrong_response_service, elicitation_wrong_response_value) =
            interaction_elicitation(&context);
        let elicitation_invalid_service = interactions(&context);
        case(
            &mut executed,
            "codex_agent::CodexInteractions::resolve_elicitation",
            "rust.service:020",
            || {
                cancel_operation(&context, 4, elicitation_cancel_service, |service| {
                    service.resolve_elicitation(&elicitation_cancel_value, &response)
                });
                operation_after_parent_drop(&context, 4, elicitation_success_service, |service| {
                    service.resolve_elicitation(&elicitation_success_value, &response)
                })
                .unwrap();
                assert!(matches!(
                    elicitation_invalid_service.resolve_elicitation(
                        &PendingElicitation::new(elicitation_success_value.elicitation.clone()),
                        &response,
                    ),
                    Err(CodexError {
                        status: Status::InvalidArgument,
                        ..
                    })
                ));
                assert_invalid_start(
                    elicitation_wrong_native_service
                        .resolve_elicitation(&elicitation_wrong_native_value, &response),
                    "elicitation native identity payload must be passed unchanged",
                );
                assert_invalid_start(
                    elicitation_wrong_response_service.resolve_elicitation(
                        &elicitation_wrong_response_value,
                        &wrong_action_response,
                    ),
                    "elicitation action must be encoded exactly",
                );
                assert_invalid_start(
                    elicitation_wrong_response_service.resolve_elicitation(
                        &elicitation_wrong_response_value,
                        &wrong_content_response,
                    ),
                    "elicitation content must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexInteractions::state",
            "rust.service:023",
            || {
                let service = interactions(&context);
                let observable = service.state().unwrap();
                let (state, _) = state_behavior(&context, 4, service, observable);
                assert_eq!(state.pending.len(), 1);
                let crate::PendingInteraction::Approval(pending) = &state.pending[0] else {
                    panic!("fixture interaction state must contain one approval")
                };
                assert!(pending.binding_identity().is_some());
                assert!(
                    PendingApproval::new(
                        pending.request_id.clone(),
                        pending.conversation_id.clone(),
                        pending.title.clone(),
                        pending.details.clone(),
                    )
                    .binding_identity()
                    .is_none(),
                    "equal user-created values must not forge native identity"
                );
            },
        );

        let added = case(
            &mut executed,
            "codex_agent::CodexMcpServers::add",
            "rust.service:024",
            || {
                let added =
                    operation_after_parent_drop(&context, 5, mcp_servers(&context), |service| {
                        service.add(&mcp_configuration())
                    })
                    .unwrap();
                let mut wrong = mcp_configuration();
                wrong.is_required = true;
                assert_invalid_start(
                    mcp_servers(&context).add(&wrong),
                    "MCP configuration payload and flags must be encoded exactly",
                );
                added
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexMcpServers::list",
            "rust.service:025",
            || {
                let values =
                    operation_after_parent_drop(&context, 5, mcp_servers(&context), |service| {
                        service.list()
                    })
                    .unwrap();
                assert_eq!(
                    values
                        .iter()
                        .map(|value| value.name.as_str())
                        .collect::<Vec<_>>(),
                    ["server-a", "server-b", "server-a"]
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexMcpServers::remove",
            "rust.service:026",
            || {
                operation_after_parent_drop(&context, 5, mcp_servers(&context), |service| {
                    service.remove(&added)
                })
                .unwrap();
                let mut wrong = added.clone();
                wrong.name = "wrong-server".into();
                assert_invalid_start(
                    mcp_servers(&context).remove(&wrong),
                    "MCP server payload must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexMcpServers::is_available",
            "rust.service:027",
            || {
                availability_behavior(&context, 5, mcp_servers(&context), |service| {
                    service.is_available()
                })
            },
        );

        case(
            &mut executed,
            "codex_agent::CodexModels::list",
            "rust.service:028",
            || {
                let values =
                    operation_after_parent_drop(&context, 6, models(&context), |service| {
                        service.list()
                    })
                    .unwrap();
                assert_eq!(
                    values
                        .iter()
                        .map(|value| value.id.as_str())
                        .collect::<Vec<_>>(),
                    ["model-a", "model-b", "model-a"]
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexModels::resolve_effort",
            "rust.service:029",
            || {
                assert_eq!(
                    operation_after_parent_drop(&context, 6, models(&context), |service| {
                        service.resolve_effort(&model(), Resolution::Preferred)
                    })
                    .unwrap(),
                    "medium"
                );
                let mut wrong = model();
                wrong.default_effort = "wrong-effort".into();
                assert_invalid_start(
                    models(&context).resolve_effort(&wrong, Resolution::Preferred),
                    "model payload must be encoded exactly for effort resolution",
                );
                assert_invalid_start(
                    models(&context).resolve_effort(&model(), Resolution::Default),
                    "effort resolution enum must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexModels::resolve_service_tier",
            "rust.service:030",
            || {
                let some = operation_after_parent_drop(&context, 6, models(&context), |service| {
                    service.resolve_service_tier(&model(), Resolution::Preferred)
                })
                .unwrap();
                assert_eq!(some.unwrap().id, "fast");
                set_leaf_fixture(
                    &context,
                    b"codex_agent_test_leaf_set_service_tier_present\0",
                    0,
                );
                assert!(
                    operation_after_parent_drop(&context, 6, models(&context), |service| {
                        service.resolve_service_tier(&model(), Resolution::Preferred)
                    })
                    .unwrap()
                    .is_none(),
                    "service-tier projection covers nullable None"
                );
                set_leaf_fixture(
                    &context,
                    b"codex_agent_test_leaf_set_service_tier_present\0",
                    1,
                );
                let mut wrong = model();
                wrong.id = "wrong-model".into();
                assert_invalid_start(
                    models(&context).resolve_service_tier(&wrong, Resolution::Preferred),
                    "model payload must be encoded exactly for service-tier resolution",
                );
                assert_invalid_start(
                    models(&context).resolve_service_tier(&model(), Resolution::First),
                    "service-tier resolution enum must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexModels::resolve",
            "rust.service:031",
            || {
                assert_eq!(
                    operation_after_parent_drop(&context, 6, models(&context), |service| {
                        service.resolve(Resolution::First)
                    })
                    .unwrap()
                    .id,
                    "model"
                );
                assert_invalid_start(
                    models(&context).resolve(Resolution::Default),
                    "model resolution must be copied exactly",
                );
            },
        );

        case(
            &mut executed,
            "codex_agent::CodexPlugins::install",
            "rust.service:032",
            || {
                assert!(
                    operation_after_parent_drop(&context, 7, plugins(&context), |service| {
                        service.install(&plugin())
                    })
                    .unwrap()
                    .connectors_needing_authentication
                    .is_empty()
                );
                let mut wrong = plugin();
                wrong.id = "wrong-plugin".into();
                assert_invalid_start(
                    plugins(&context).install(&wrong),
                    "installed plugin reference must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexPlugins::list",
            "rust.service:033",
            || {
                assert!(
                    operation_after_parent_drop(&context, 7, plugins(&context), |service| {
                        service.list(true)
                    })
                    .unwrap()
                    .plugins
                    .is_empty()
                );
                assert_invalid_start(
                    plugins(&context).list(false),
                    "plugin force-refresh flag must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexPlugins::read",
            "rust.service:034",
            || {
                assert_eq!(
                    operation_after_parent_drop(&context, 7, plugins(&context), |service| {
                        service.read(&plugin())
                    })
                    .unwrap()
                    .summary
                    .reference
                    .id,
                    "plugin-id"
                );
                let mut wrong = plugin();
                wrong.marketplace_name = "wrong-market".into();
                assert_invalid_start(
                    plugins(&context).read(&wrong),
                    "read plugin reference must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexPlugins::uninstall",
            "rust.service:035",
            || {
                operation_after_parent_drop(&context, 7, plugins(&context), |service| {
                    service.uninstall(&plugin())
                })
                .unwrap();
                let mut wrong = plugin();
                wrong.name = "wrong-plugin".into();
                assert_invalid_start(
                    plugins(&context).uninstall(&wrong),
                    "uninstalled plugin reference must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexPlugins::is_available",
            "rust.service:036",
            || {
                availability_behavior(&context, 7, plugins(&context), |service| {
                    service.is_available()
                })
            },
        );

        let skill = case(
            &mut executed,
            "codex_agent::CodexSkills::install",
            "rust.service:037",
            || {
                let installed =
                    operation_after_parent_drop(&context, 8, skills(&context), |service| {
                        service.install("skills", InstallationScope::Workspace)
                    })
                    .unwrap();
                assert_invalid_start(
                    skills(&context).install("wrong-skills", InstallationScope::Workspace),
                    "skill path must be copied exactly",
                );
                assert_invalid_start(
                    skills(&context).install("skills", InstallationScope::User),
                    "skill scope must be copied exactly",
                );
                installed
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexSkills::list",
            "rust.service:038",
            || {
                assert!(
                    operation_after_parent_drop(&context, 8, skills(&context), |service| {
                        service.list(true)
                    })
                    .unwrap()
                    .skills
                    .is_empty()
                );
                assert_invalid_start(
                    skills(&context).list(false),
                    "skill force-refresh flag must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexSkills::read",
            "rust.service:039",
            || {
                assert_eq!(
                    operation_after_parent_drop(&context, 8, skills(&context), |service| {
                        service.read("skill.md", 7)
                    })
                    .unwrap()
                    .content,
                    "content"
                );
                assert_invalid_start(
                    skills(&context).read("wrong-skill.md", 7),
                    "skill read path must be copied exactly",
                );
                assert_invalid_start(
                    skills(&context).read("skill.md", 8),
                    "skill read offset must be copied exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexSkills::uninstall",
            "rust.service:040",
            || {
                operation_after_parent_drop(&context, 8, skills(&context), |service| {
                    service.uninstall(&skill)
                })
                .unwrap();
                let mut wrong = skill.clone();
                wrong.path = "wrong-skill.md".into();
                assert_invalid_start(
                    skills(&context).uninstall(&wrong),
                    "uninstalled skill value must be encoded exactly",
                );
            },
        );
        case(
            &mut executed,
            "codex_agent::CodexSkills::is_available",
            "rust.service:041",
            || {
                availability_behavior(&context, 8, skills(&context), |service| {
                    service.is_available()
                })
            },
        );

        assert_eq!(
            executed.len(),
            42,
            "exact per-capability service behavior cases"
        );
        for index in 0..42 {
            assert!(executed.contains(&format!("rust.service:{index:03}")));
        }
    }

    #[test]
    fn all_11_agent_properties_execute_through_the_production_wrapper() {
        let _call_session = crate::ffi::test_call_session();
        use crate::{ClientInfo, CodexHost, HostOptions};

        let native = crate::CodexNativeLibrary::load(fixture()).expect("load Agent fixture");
        let host = CodexHost::create_with_library(
            &native,
            HostOptions {
                bundle_directory: "/bundle".into(),
                data_directory: "/data".into(),
                client_info: ClientInfo {
                    name: "rust".into(),
                    title: "Rust".into(),
                    version: "1.95".into(),
                },
            },
        )
        .expect("create Agent host");
        block_on(host.start().expect("start Agent host")).expect("complete Agent host start");
        let agent = host.agent().expect("acquire ready Agent");
        let context = agent.inner.handle.context.clone();
        let mut executed = BTreeSet::new();

        set_leaf_fixture(&context, b"codex_agent_test_leaf_set_completion_mode\0", 1);
        set_leaf_fixture(&context, b"codex_agent_test_leaf_set_terminal\0", 1);
        set_leaf_fixture(&context, b"codex_agent_test_leaf_set_result\0", 0);

        type Counter = unsafe extern "C" fn() -> i32;
        let children: Counter = symbol(&context, b"codex_agent_test_agent_children_live\0")
            .expect("load Agent-child counter");
        let release_errors: Counter = symbol(
            &context,
            b"codex_agent_test_agent_release_with_live_children_errors\0",
        )
        .expect("load premature Agent-release counter");
        let workspace_destroys: Counter =
            symbol(&context, b"codex_agent_test_workspace_destroy_count\0")
                .expect("load workspace destroy counter");
        let child_count = || {
            // SAFETY: this test control is a no-argument atomic counter snapshot.
            unsafe { children() }
        };
        let release_error_count = || {
            // SAFETY: this test control is a no-argument atomic counter snapshot.
            unsafe { release_errors() }
        };
        let workspace_destroy_count = || {
            // SAFETY: this test control is a no-argument atomic counter snapshot.
            unsafe { workspace_destroys() }
        };

        assert_eq!(child_count(), 0, "Agent starts without retained children");
        let release_error_before = release_error_count();
        let agent_releases_before = release_log(&context)
            .into_iter()
            .filter(|value| *value == b'A')
            .count();
        let leaf_releases_before = (0..9)
            .map(|kind| leaf_release_count(&context, kind))
            .collect::<Vec<_>>();

        crate::ffi::test_clear_calls();
        type AuthenticationGet = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::Authentication,
        ) -> i32;
        let _: AuthenticationGet = symbol(&context, b"codex_agent_agent_authentication\0")
            .expect("resolve exact Agent negative lookup");
        assert!(
            crate::ffi::test_calls().is_empty(),
            "successful Agent-symbol lookup is not invocation evidence"
        );

        let authentication = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::authentication",
            "rust.agent:000",
            || {
                let first = agent.authentication().unwrap();
                let second = agent.authentication().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let connectors = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::connectors",
            "rust.agent:001",
            || {
                let first = agent.connectors().unwrap();
                let second = agent.connectors().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let conversations = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::conversations",
            "rust.agent:002",
            || {
                let first = agent.conversations().unwrap();
                let second = agent.conversations().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let hooks = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::hooks",
            "rust.agent:003",
            || {
                let first = agent.hooks().unwrap();
                let second = agent.hooks().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let authorization = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::integration_authorization",
            "rust.agent:004",
            || {
                let first = agent.integration_authorization().unwrap();
                let second = agent.integration_authorization().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let interactions = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::interactions",
            "rust.agent:005",
            || {
                let first = agent.interactions().unwrap();
                let second = agent.interactions().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let mcp_servers = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::mcp_servers",
            "rust.agent:006",
            || {
                let first = agent.mcp_servers().unwrap();
                let second = agent.mcp_servers().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let models = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::models",
            "rust.agent:007",
            || {
                let first = agent.models().unwrap();
                let second = agent.models().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let plugins = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::plugins",
            "rust.agent:008",
            || {
                let first = agent.plugins().unwrap();
                let second = agent.plugins().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let skills = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::skills",
            "rust.agent:009",
            || {
                let first = agent.skills().unwrap();
                let second = agent.skills().unwrap();
                assert!(Arc::ptr_eq(&first.inner, &second.inner));
                first
            },
        );
        let workspace_destroy_before = workspace_destroy_count();
        let workspace = agent_case(
            &mut executed,
            "codex_agent::CodexAgent::workspace",
            "rust.agent:010",
            || {
                let first = agent.workspace().unwrap();
                let second = agent.workspace().unwrap();
                assert_eq!(
                    first, second,
                    "cached workspace preserves exact value identity"
                );
                first
            },
        );
        assert_eq!(workspace.path, "/agent-workspace");
        assert_eq!(workspace.display_name, "Agent Workspace");
        assert_eq!(
            workspace_destroy_count(),
            workspace_destroy_before + 1,
            "native workspace snapshot is destroyed immediately after copying"
        );
        assert_eq!(
            child_count(),
            10,
            "nine services plus conversations are live"
        );

        drop(agent);
        assert_eq!(
            release_log(&context)
                .into_iter()
                .filter(|value| *value == b'A')
                .count(),
            agent_releases_before,
            "service projections retain the Agent after the public owner is dropped"
        );
        assert_eq!(release_error_count(), release_error_before);
        assert_eq!(child_count(), 10);

        let _ = authentication.state().unwrap().current().unwrap();
        assert!(connectors.is_available().unwrap());
        let _ = conversations.active().unwrap().current().unwrap();
        assert!(hooks.is_available().unwrap());
        let _ = authorization.state().unwrap().current().unwrap();
        let _ = interactions.state().unwrap().current().unwrap();
        assert!(mcp_servers.is_available().unwrap());
        assert_eq!(block_on(models.list().unwrap()).unwrap().len(), 3);
        assert!(plugins.is_available().unwrap());
        assert!(skills.is_available().unwrap());

        drop(authentication);
        drop(connectors);
        drop(hooks);
        drop(authorization);
        drop(interactions);
        drop(mcp_servers);
        drop(models);
        drop(plugins);
        drop(skills);
        drop(conversations);
        wait_for_count(
            || -child_count(),
            0,
            "all native children to release before Agent",
        );
        assert_eq!(child_count(), 0, "all native children release before Agent");
        assert_eq!(release_error_count(), release_error_before);
        wait_for_count(
            || {
                release_log(&context)
                    .into_iter()
                    .filter(|value| *value == b'A')
                    .count() as i32
            },
            (agent_releases_before + 1) as i32,
            "Agent release after its last child",
        );
        assert_eq!(
            release_log(&context)
                .into_iter()
                .filter(|value| *value == b'A')
                .count(),
            agent_releases_before + 1,
            "Agent releases exactly once after its last child"
        );
        for (kind, before) in leaf_releases_before.into_iter().enumerate() {
            assert_eq!(
                leaf_release_count(&context, kind as i32),
                before + 1,
                "Agent-owned leaf service {kind} releases exactly once"
            );
        }

        block_on(host.close().unwrap()).unwrap();
        drop(host);
        assert_eq!(workspace.path, "/agent-workspace");
        assert_eq!(workspace.display_name, "Agent Workspace");
        assert_eq!(executed.len(), 11);
        for index in 0..11 {
            assert!(executed.contains(&format!("rust.agent:{index:03}")));
        }

        let authentication_calls =
            exact_claim_calls("codex_agent::CodexAgent::authentication", "rust.agent:000");
        let connectors_calls =
            exact_claim_calls("codex_agent::CodexAgent::connectors", "rust.agent:001");
        assert!(
            validate_agent_invocations(&authentication_calls, &connectors_calls).is_err(),
            "wrong Agent method fails closed"
        );
        assert!(
            validate_agent_invocations(
                &authentication_calls,
                &BTreeSet::from(["codex_agent_removed_stale_trace".into()])
            )
            .is_err(),
            "stale Agent trace fails closed"
        );
    }

    #[test]
    fn all_7_host_ready_capabilities_execute_through_the_production_wrapper() {
        let _call_session = crate::ffi::test_call_session();
        use crate::{ClientInfo, CodexHost, HostOptions, HostStateKind, HostStateReady};

        fn options(values: [&str; 5]) -> HostOptions {
            HostOptions {
                bundle_directory: values[0].into(),
                data_directory: values[1].into(),
                client_info: ClientInfo {
                    name: values[2].into(),
                    title: values[3].into(),
                    version: values[4].into(),
                },
            }
        }

        let expected_options = [
            "/host-bundle",
            "/host-data",
            "host-client",
            "Host Client",
            "1.0",
        ];
        let native = crate::CodexNativeLibrary::load(fixture()).expect("load Host fixture");
        let control_context = context();
        let mut executed = BTreeSet::new();

        type CopiedHostOptionEquals = unsafe extern "C" fn(i32, *const ffi::StringView) -> i32;
        type CopiedSelectionEquals = unsafe extern "C" fn(*const ffi::StringView) -> i32;
        type SetHostState = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Host, i32) -> i32;
        type StatusAction = unsafe extern "C" fn() -> i32;
        type VoidAction = unsafe extern "C" fn();
        let copied_option: CopiedHostOptionEquals = symbol(
            &control_context,
            b"codex_agent_test_copied_host_option_equals\0",
        )
        .expect("load exact copied Host-option comparison");
        let copied_selection: CopiedSelectionEquals = symbol(
            &control_context,
            b"codex_agent_test_copied_workspace_selection_equals\0",
        )
        .expect("load exact copied workspace comparison");

        let host = host_case(
            &mut executed,
            "codex_agent::CodexHost::create",
            "rust.host:002",
            || {
                set_leaf_fixture(
                    &control_context,
                    b"codex_agent_test_require_exact_host_inputs\0",
                    1,
                );
                for index in 0..expected_options.len() {
                    let mut wrong = expected_options;
                    wrong[index] = "wrong-but-nonblank";
                    let error = CodexHost::create_with_library(&native, options(wrong))
                        .err()
                        .expect("each wrong copied Host option must fail closed");
                    assert_eq!(error.status, Status::InvalidArgument);
                }
                let host = CodexHost::create_with_library(&native, options(expected_options))
                    .expect("create exact copied Host");
                for (index, expected) in expected_options.iter().enumerate() {
                    let expected = ffi::StringView::new(expected);
                    // SAFETY: the fixture immediately borrows this exact UTF-8 view.
                    assert_eq!(unsafe { copied_option(index as i32, &expected) }, 1);
                }
                set_leaf_fixture(
                    &control_context,
                    b"codex_agent_test_require_exact_host_inputs\0",
                    0,
                );
                host
            },
        );
        let constructor_context = host.inner.handle.context.clone();
        let host_releases_before = release_log(&constructor_context)
            .into_iter()
            .filter(|value| *value == b'H')
            .count();
        block_on(host.close().unwrap()).unwrap();
        drop(host);
        wait_for_count(
            || {
                release_log(&constructor_context)
                    .into_iter()
                    .filter(|value| *value == b'H')
                    .count() as i32
            },
            (host_releases_before + 1) as i32,
            "constructed Host release",
        );
        assert_eq!(
            release_log(&constructor_context)
                .into_iter()
                .filter(|value| *value == b'H')
                .count(),
            host_releases_before + 1,
            "constructed Host owns and releases its exact native parent"
        );

        let ready_constructor_host =
            CodexHost::create_with_library(&native, options(expected_options)).unwrap();
        block_on(ready_constructor_host.start().unwrap()).unwrap();
        let ready_constructor = host_case(
            &mut executed,
            "codex_agent::HostStateReady::new",
            "rust.host:000",
            || {
                let state = ready_constructor_host.state().unwrap();
                assert_eq!(state.kind, HostStateKind::Ready);
                assert_eq!(state.workspace.as_ref().unwrap().path, "/tmp/workspace");
                let ready = state.ready.expect("typed Ready payload");
                let rebuilt = HostStateReady::new(ready.agent());
                assert_eq!(ready.agent(), rebuilt.agent());
                rebuilt
            },
        );
        let ready_agent = ready_constructor.agent();
        block_on(ready_constructor_host.close().unwrap()).unwrap();
        let release_before = release_log(&ready_agent.inner.handle.context)
            .into_iter()
            .filter(|value| *value == b'H')
            .count();
        drop(ready_constructor_host);
        assert_eq!(
            release_log(&ready_agent.inner.handle.context)
                .into_iter()
                .filter(|value| *value == b'H')
                .count(),
            release_before,
            "Ready Agent retains its Host parent"
        );
        let ready_context = ready_agent.inner.handle.context.clone();
        drop(ready_agent);
        drop(ready_constructor);
        wait_for_count(
            || {
                release_log(&ready_context)
                    .into_iter()
                    .filter(|value| *value == b'H')
                    .count() as i32
            },
            (release_before + 1) as i32,
            "Ready-owned Host release",
        );
        assert_eq!(
            release_log(&ready_context)
                .into_iter()
                .filter(|value| *value == b'H')
                .count(),
            release_before + 1,
            "Ready Agent releases before its Host parent"
        );

        let ready_property_host =
            CodexHost::create_with_library(&native, options(expected_options)).unwrap();
        block_on(ready_property_host.start().unwrap()).unwrap();
        let ready_property = host_case(
            &mut executed,
            "codex_agent::HostStateReady::agent",
            "rust.host:001",
            || ready_property_host.state().unwrap().ready.unwrap(),
        );
        let ready_property_agent = ready_property.agent();
        assert_eq!(ready_property_agent, ready_property.agent());
        block_on(ready_property_host.close().unwrap()).unwrap();
        let ready_property_context = ready_property_agent.inner.handle.context.clone();
        let release_before = release_log(&ready_property_context)
            .into_iter()
            .filter(|value| *value == b'H')
            .count();
        drop(ready_property_host);
        assert_eq!(
            release_log(&ready_property_context)
                .into_iter()
                .filter(|value| *value == b'H')
                .count(),
            release_before,
            "Ready property retains the Host through its identity-stable Agent"
        );
        drop(ready_property_agent);
        drop(ready_property);
        wait_for_count(
            || {
                release_log(&ready_property_context)
                    .into_iter()
                    .filter(|value| *value == b'H')
                    .count() as i32
            },
            (release_before + 1) as i32,
            "Ready-property-owned Host release",
        );
        assert_eq!(
            release_log(&ready_property_context)
                .into_iter()
                .filter(|value| *value == b'H')
                .count(),
            release_before + 1
        );

        let start_host =
            CodexHost::create_with_library(&native, options(expected_options)).unwrap();
        let start_context = start_host.inner.handle.context.clone();
        host_case(
            &mut executed,
            "codex_agent::CodexHost::start",
            "rust.host:005",
            || {
                exercise_host_operation(&start_context, &start_host.inner, || start_host.start());
            },
        );
        assert_eq!(start_host.state().unwrap().kind, HostStateKind::Ready);
        block_on(start_host.close().unwrap()).unwrap();
        let releases_before = release_log(&start_context)
            .into_iter()
            .filter(|value| *value == b'H')
            .count();
        drop(start_host);
        wait_for_count(
            || {
                release_log(&start_context)
                    .into_iter()
                    .filter(|value| *value == b'H')
                    .count() as i32
            },
            (releases_before + 1) as i32,
            "started Host release",
        );

        let selection_host =
            CodexHost::create_with_library(&native, options(expected_options)).unwrap();
        let selection_context = selection_host.inner.handle.context.clone();
        host_case(
            &mut executed,
            "codex_agent::CodexHost::select_workspace",
            "rust.host:004",
            || {
                set_leaf_fixture(
                    &selection_context,
                    b"codex_agent_test_require_exact_host_inputs\0",
                    1,
                );
                let error = selection_host
                    .select_workspace("/wrong-workspace")
                    .err()
                    .expect("wrong copied workspace selection fails closed");
                assert_eq!(error.status, Status::InvalidArgument);
                let wrong = ffi::StringView::new("/wrong-workspace");
                // SAFETY: the fixture immediately borrows this exact UTF-8 view.
                assert_eq!(unsafe { copied_selection(&wrong) }, 1);
                exercise_host_operation(&selection_context, &selection_host.inner, || {
                    selection_host.select_workspace("/selected-workspace")
                });
                let expected = ffi::StringView::new("/selected-workspace");
                // SAFETY: the fixture immediately borrows this exact UTF-8 view.
                assert_eq!(unsafe { copied_selection(&expected) }, 1);
                set_leaf_fixture(
                    &selection_context,
                    b"codex_agent_test_require_exact_host_inputs\0",
                    0,
                );
            },
        );
        block_on(selection_host.close().unwrap()).unwrap();
        let releases_before = release_log(&selection_context)
            .into_iter()
            .filter(|value| *value == b'H')
            .count();
        drop(selection_host);
        wait_for_count(
            || {
                release_log(&selection_context)
                    .into_iter()
                    .filter(|value| *value == b'H')
                    .count() as i32
            },
            (releases_before + 1) as i32,
            "workspace-selected Host release",
        );

        let close_host =
            CodexHost::create_with_library(&native, options(expected_options)).unwrap();
        let close_context = close_host.inner.handle.context.clone();
        host_case(
            &mut executed,
            "codex_agent::CodexHost::close",
            "rust.host:003",
            || {
                exercise_host_operation(&close_context, &close_host.inner, || close_host.close());
                block_on(close_host.close().unwrap()).expect("repeated close is idempotent");
                block_on(close_host.close().unwrap()).expect("third close remains idempotent");
            },
        );
        let releases_before = release_log(&close_context)
            .into_iter()
            .filter(|value| *value == b'H')
            .count();
        drop(close_host);
        wait_for_count(
            || {
                release_log(&close_context)
                    .into_iter()
                    .filter(|value| *value == b'H')
                    .count() as i32
            },
            (releases_before + 1) as i32,
            "repeatedly closed Host release",
        );

        let state_host =
            CodexHost::create_with_library(&native, options(expected_options)).unwrap();
        let state_context = state_host.inner.handle.context.clone();
        let raw_host = state_host.inner.handle.ptr().unwrap();
        let set_host_state: SetHostState =
            symbol(&state_context, b"codex_agent_test_set_host_state\0")
                .expect("load exact Host-state setter");
        let publish_state: StatusAction = symbol(
            &state_context,
            b"codex_agent_test_publish_host_state_status\0",
        )
        .expect("load exact Host-state publisher");
        let finish_state: VoidAction =
            symbol(&state_context, b"codex_agent_test_finish_host_state\0")
                .expect("load exact Host-state terminal publisher");
        let subscriptions_before = subscription_destroy_count(&state_context);
        let (ready_from_stream, ready_from_current, authentication, copied_workspace) = host_case(
            &mut executed,
            "codex_agent::CodexHost::state",
            "rust.host:006",
            || {
                assert_eq!(state_host.state().unwrap().kind, HostStateKind::New);
                let mut states = state_host.states().unwrap();
                let current = block_on(states.next()).unwrap().unwrap();
                assert_eq!(current.kind, HostStateKind::New);
                assert!(current.ready.is_none());

                // SAFETY: raw_host belongs to state_context and 4 is the exact Ready enum value.
                let status = unsafe { set_host_state(state_context.ptr(), raw_host, 4) };
                assert_eq!(status, 0);
                // SAFETY: the fixture publishes to the one currently owned Host subscription.
                assert_eq!(unsafe { publish_state() }, 0);
                let later = block_on(states.next()).unwrap().unwrap();
                assert_eq!(later.kind, HostStateKind::Ready);
                assert_ne!(
                    later, current,
                    "Host stream emits a genuinely distinct update"
                );
                let copied_workspace = later.workspace.clone().unwrap();
                assert_eq!(copied_workspace.path, "/tmp/workspace");
                assert_eq!(copied_workspace.display_name, "Workspace");
                let ready_from_stream = later.ready.as_ref().unwrap().agent();

                let direct = state_host.state().unwrap();
                let ready_from_current = direct.ready.as_ref().unwrap().agent();
                assert_eq!(ready_from_stream, ready_from_current);

                // SAFETY: this terminates the exact active fixture subscription.
                unsafe { finish_state() };
                assert!(block_on(states.next()).is_none());
                drop(states);

                let cancelled = state_host.states().unwrap();
                drop(cancelled);
                wait_for_count(
                    || subscription_destroy_count(&state_context),
                    subscriptions_before + 2,
                    "terminal and cancelled Host subscriptions",
                );
                // SAFETY: cancellation must have detached the sole fixture subscription.
                assert_eq!(unsafe { publish_state() }, ffi::STATUS_NOT_READY);

                let authentication = ready_from_current.authentication().unwrap();
                (
                    ready_from_stream,
                    ready_from_current,
                    authentication,
                    copied_workspace,
                )
            },
        );

        block_on(state_host.close().unwrap()).unwrap();
        let release_before = release_log(&state_context).len();
        drop(state_host);
        assert_eq!(
            release_log(&state_context).len(),
            release_before,
            "Ready Agent and child retain Host after public Host disposal"
        );
        drop(ready_from_stream);
        drop(ready_from_current);
        assert_eq!(
            release_log(&state_context).len(),
            release_before,
            "leaf child retains Agent and Host"
        );
        drop(authentication);
        wait_for_count(
            || release_log(&state_context).len() as i32,
            (release_before + 2) as i32,
            "Agent then Host release",
        );
        let released = release_log(&state_context);
        assert_eq!(
            released[release_before..],
            [b'A', b'H'],
            "Agent releases after its last child and before Host"
        );
        assert_eq!(copied_workspace.path, "/tmp/workspace");
        assert_eq!(copied_workspace.display_name, "Workspace");

        set_leaf_fixture(
            &control_context,
            b"codex_agent_test_set_host_operation_result\0",
            ffi::STATUS_OK,
        );
        set_leaf_fixture(
            &control_context,
            b"codex_agent_test_set_host_operation_completion_mode\0",
            1,
        );
        set_leaf_fixture(
            &control_context,
            b"codex_agent_test_require_exact_host_inputs\0",
            0,
        );
        assert_eq!(executed.len(), 7, "exact per-capability Host/Ready cases");
        for index in 0..7 {
            assert!(executed.contains(&format!("rust.host:{index:03}")));
        }

        let start_calls = exact_claim_calls("codex_agent::CodexHost::start", "rust.host:005");
        let close_calls = exact_claim_calls("codex_agent::CodexHost::close", "rust.host:003");
        assert!(
            validate_host_invocations(&start_calls, &close_calls).is_err(),
            "wrong Host method fails closed"
        );
        assert!(
            validate_host_invocations(
                &start_calls,
                &BTreeSet::from(["codex_agent_removed_stale_trace".into()])
            )
            .is_err(),
            "stale Host trace fails closed"
        );
    }

    #[test]
    fn all_20_conversation_capabilities_execute_through_the_production_wrapper() {
        let _call_session = crate::ffi::test_call_session();
        use crate::{
            ClientInfo, CodexHost, CollaborationMode, ConversationId, ConversationOpenOptions,
            HostOptions, Invocation, PluginInvocation, SkillInvocation, TurnRequest,
        };
        let native = crate::CodexNativeLibrary::load(fixture()).expect("load conversation fixture");
        let host = CodexHost::create_with_library(
            &native,
            HostOptions {
                bundle_directory: "/bundle".into(),
                data_directory: "/data".into(),
                client_info: ClientInfo {
                    name: "rust".into(),
                    title: "Rust".into(),
                    version: "1.95".into(),
                },
            },
        )
        .expect("create conversation host");
        block_on(host.start().expect("start host")).expect("ready host");
        let agent = host.agent().expect("ready agent");
        let conversations = agent.conversations().expect("conversation service");
        let context = conversations.inner.handle.context.clone();
        set_conversation_fixture(&context, b"codex_agent_test_conversation_mode\0", 1);
        set_conversation_fixture(&context, b"codex_agent_test_conversation_terminal\0", 1);
        let mut executed = BTreeSet::new();

        let (absent_open, conversation) = conversation_case(
            &mut executed,
            "codex_agent::CodexConversations::open",
            "rust.conversation:002",
            || {
                let before = stable_strong_count(&conversations.inner);
                let absent = finish_retained(
                    &conversations.inner,
                    before,
                    conversations
                        .open(ConversationOpenOptions::default())
                        .unwrap(),
                )
                .unwrap();
                assert!(
                    conversations
                        .open(ConversationOpenOptions {
                            conversation_id: Some("wrong-open".into()),
                            approval_preset: Some(crate::ApprovalPreset::AskMe),
                            service_tier: Some("fast".into()),
                        })
                        .is_err(),
                    "wrong open ID fails closed"
                );
                assert!(
                    conversations
                        .open(ConversationOpenOptions {
                            conversation_id: Some("conversation-open".into()),
                            approval_preset: Some(crate::ApprovalPreset::Never),
                            service_tier: Some("fast".into()),
                        })
                        .is_err(),
                    "wrong open settings fail closed"
                );
                assert!(
                    conversations
                        .open(ConversationOpenOptions {
                            conversation_id: Some("conversation-open".into()),
                            approval_preset: Some(crate::ApprovalPreset::AskMe),
                            service_tier: Some("wrong-tier".into()),
                        })
                        .is_err(),
                    "wrong open service tier fails closed independently"
                );
                let before = stable_strong_count(&conversations.inner);
                let opened = finish_retained(
                    &conversations.inner,
                    before,
                    conversations
                        .open(ConversationOpenOptions {
                            conversation_id: Some("conversation-open".into()),
                            approval_preset: Some(crate::ApprovalPreset::AskMe),
                            service_tier: Some("fast".into()),
                        })
                        .unwrap(),
                )
                .unwrap();
                assert!(
                    opened.is_same(&opened).unwrap(),
                    "opened conversation identity"
                );
                (absent, opened)
            },
        );
        block_on(absent_open.close().unwrap()).unwrap();
        drop(absent_open);

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversations::list",
            "rust.conversation:001",
            || {
                let before = stable_strong_count(&conversations.inner);
                let values =
                    finish_retained(&conversations.inner, before, conversations.list().unwrap())
                        .unwrap();
                assert_eq!(values.len(), 3);
                assert_eq!(
                    values
                        .iter()
                        .map(|value| value.conversation_id.value.as_str())
                        .collect::<Vec<_>>(),
                    [
                        "conversation-alpha",
                        "conversation-beta",
                        "conversation-alpha"
                    ]
                );
                assert_eq!(
                    (&values[0].title, values[0].updated_at_epoch_seconds),
                    (&"Alpha".into(), 11)
                );
                assert_eq!(
                    (&values[1].title, values[1].updated_at_epoch_seconds),
                    (&"Beta".into(), 22)
                );
            },
        );

        let exact_messages = |values: &[crate::Message], first: &str, second: &str| {
            assert_eq!(values.len(), 3);
            assert_eq!(
                values
                    .iter()
                    .map(|value| value.id.as_str())
                    .collect::<Vec<_>>(),
                [first, second, first]
            );
            assert_eq!(
                values[0].client_message_id.as_deref(),
                Some(if first.ends_with("alpha") {
                    "client-alpha"
                } else {
                    "client-gamma"
                })
            );
            assert_eq!(values[1].client_message_id, None);
            assert!(
                values
                    .iter()
                    .all(|value| value.role == crate::MessageRole::Assistant)
            );
            assert_eq!(
                values
                    .iter()
                    .map(|value| value.text.as_str())
                    .collect::<Vec<_>>(),
                if first.ends_with("alpha") {
                    vec!["hello-alpha", "hello-beta", "hello-alpha"]
                } else {
                    vec!["hello-gamma", "hello-delta", "hello-gamma"]
                }
            );
            assert!(
                values
                    .iter()
                    .all(|value| value.collaboration_mode == CollaborationMode::Plan)
            );
            assert_eq!(
                values[0].capabilities,
                BTreeSet::from([crate::Capability::WebSearch])
            );
            assert!(values[1].capabilities.is_empty());
            assert_eq!(
                values[0].invocations,
                vec![
                    Invocation::Plugin(PluginInvocation::new("plugin", "plugin://plugin@market")),
                    Invocation::Skill(SkillInvocation::new("skill", "skill.md")),
                ]
            );
            assert!(values[1].invocations.is_empty());
            assert_eq!(
                values[0].reasoning.as_deref(),
                Some(if first.ends_with("alpha") {
                    "reason-alpha"
                } else {
                    "reason-gamma"
                })
            );
            assert_eq!(values[1].reasoning, None);
            assert_eq!(
                values[0].plan.as_deref(),
                Some(if first.ends_with("alpha") {
                    "plan-alpha"
                } else {
                    "plan-gamma"
                })
            );
            assert_eq!(values[1].plan, None);
            assert_eq!(
                values[0].shell_command.as_deref(),
                Some(if first.ends_with("alpha") {
                    "pwd-alpha"
                } else {
                    "pwd-gamma"
                })
            );
            assert_eq!(values[1].shell_command, None);
            assert_eq!(
                values[0].exit_code,
                Some(if first.ends_with("alpha") { 7 } else { 9 })
            );
            assert_eq!(values[1].exit_code, None);
            assert_eq!(values[2], values[0], "duplicate message is exact");
        };

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversations::read",
            "rust.conversation:003",
            || {
                let before = stable_strong_count(&conversations.inner);
                let snapshot = finish_retained(
                    &conversations.inner,
                    before,
                    conversations
                        .read(&ConversationId::new("read-input").unwrap())
                        .unwrap(),
                )
                .unwrap();
                assert_eq!(snapshot.summary.conversation_id.value, "conversation-alpha");
                exact_messages(&snapshot.messages, "message-alpha", "message-beta");
                assert!(
                    conversations
                        .read(&ConversationId::new("wrong").unwrap())
                        .is_err()
                );
            },
        );

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversations::rename",
            "rust.conversation:004",
            || {
                let before = stable_strong_count(&conversations.inner);
                finish_retained(
                    &conversations.inner,
                    before,
                    conversations
                        .rename(&ConversationId::new("rename-input").unwrap(), "Renamed")
                        .unwrap(),
                )
                .unwrap();
                assert!(
                    conversations
                        .rename(&ConversationId::new("wrong").unwrap(), "Renamed")
                        .is_err()
                );
                assert!(
                    conversations
                        .rename(&ConversationId::new("rename-input").unwrap(), "Wrong")
                        .is_err()
                );
            },
        );

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversations::delete",
            "rust.conversation:000",
            || {
                let before = stable_strong_count(&conversations.inner);
                finish_retained(
                    &conversations.inner,
                    before,
                    conversations
                        .delete(&ConversationId::new("delete-input").unwrap())
                        .unwrap(),
                )
                .unwrap();
                assert!(
                    conversations
                        .delete(&ConversationId::new("wrong").unwrap())
                        .is_err()
                );
            },
        );

        let mut retained_active = Vec::new();
        conversation_case(
            &mut executed,
            "codex_agent::CodexConversations::active",
            "rust.conversation:005",
            || {
                let before = stable_strong_count(&conversations.inner);
                let state = conversations.active().unwrap();
                assert!(Arc::strong_count(&conversations.inner) > before);
                let current = state.current().unwrap().expect("active current");
                assert!(conversation.is_same(&current).unwrap());
                retained_active.push(current);
                let mut stream = state.subscribe().unwrap();
                let initial = block_on(stream.next())
                    .unwrap()
                    .unwrap()
                    .expect("active initial");
                assert!(conversation.is_same(&initial).unwrap());
                retained_active.push(initial);
                assert!(block_on(stream.next()).unwrap().unwrap().is_none());
                assert!(block_on(stream.next()).is_none());
                drop(stream);
                let destroyed = subscription_destroy_count(&context);
                set_conversation_fixture(&context, b"codex_agent_test_conversation_terminal\0", 0);
                let cancelled = state.subscribe().unwrap();
                drop(cancelled);
                wait_for_count(
                    || subscription_destroy_count(&context),
                    destroyed + 1,
                    "active cancellation",
                );
                type Publish = unsafe extern "C" fn(*mut ffi::Context) -> i32;
                let publish: Publish = symbol(
                    &context,
                    b"codex_agent_test_conversation_publish_after_cancel\0",
                )
                .unwrap();
                let mut status = ffi::STATUS_OK;
                for _ in 0..2_000 {
                    // SAFETY: the test context remains alive for the duration of this exact hook call.
                    status = unsafe { publish(context.ptr()) };
                    if status == ffi::STATUS_NOT_READY {
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(1));
                }
                assert_eq!(status, ffi::STATUS_NOT_READY);
                set_conversation_fixture(&context, b"codex_agent_test_conversation_terminal\0", 1);
                drop(state);
                assert_eq!(
                    Arc::strong_count(&conversations.inner),
                    before + retained_active.len()
                );
            },
        );

        for (symbol, test, operation) in [
            (
                "codex_agent::CodexConversation::cancel_turn",
                "rust.conversation:006",
                0,
            ),
            (
                "codex_agent::CodexConversation::reload",
                "rust.conversation:008",
                1,
            ),
        ] {
            conversation_case(&mut executed, symbol, test, || {
                let before = stable_strong_count(&conversation.inner);
                let value = if operation == 0 {
                    conversation.cancel_turn()
                } else {
                    conversation.reload()
                };
                finish_retained(&conversation.inner, before, value.unwrap()).unwrap();
            });
        }

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::run_shell_command",
            "rust.conversation:009",
            || {
                let before = stable_strong_count(&conversation.inner);
                finish_retained(
                    &conversation.inner,
                    before,
                    conversation.run_shell_command("pwd").unwrap(),
                )
                .unwrap();
                assert!(conversation.run_shell_command("wrong-shell").is_err());
                let pending = conversation.run_shell_command("sleep").unwrap();
                pending.cancel().unwrap();
                assert_eq!(block_on(pending).unwrap_err().status, Status::Cancelled);
            },
        );

        let request = TurnRequest::new(
            "structured",
            Some("client-1".into()),
            Some("model".into()),
            Some("high".into()),
            Some("fast".into()),
            crate::ApprovalPreset::AskMe,
            BTreeSet::from([crate::Capability::WebSearch]),
            vec![
                Invocation::Plugin(PluginInvocation::new("plugin", "plugin://plugin@market")),
                Invocation::Skill(SkillInvocation::new("skill", "skill.md")),
            ],
            CollaborationMode::Plan,
        );
        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::send_request",
            "rust.conversation:010",
            || {
                let before = stable_strong_count(&conversation.inner);
                finish_retained(
                    &conversation.inner,
                    before,
                    conversation.send_request(&request).unwrap(),
                )
                .unwrap();
                let rejects = |description: &str, mutate: fn(&mut TurnRequest)| {
                    let mut wrong = request.clone();
                    mutate(&mut wrong);
                    assert!(
                        conversation.send_request(&wrong).is_err(),
                        "wrong {description} must fail closed"
                    );
                };
                rejects("prompt", |value| value.prompt = "wrong".into());
                rejects("client message ID", |value| {
                    value.client_message_id = Some("wrong".into());
                });
                rejects("model", |value| value.model = Some("wrong".into()));
                rejects("effort", |value| value.effort = Some("wrong".into()));
                rejects("service tier", |value| {
                    value.service_tier = Some("wrong".into());
                });
                rejects("approval preset", |value| {
                    value.approval_preset = crate::ApprovalPreset::Strict;
                });
                rejects("capabilities", |value| value.capabilities.clear());
                rejects("collaboration mode", |value| {
                    value.collaboration_mode = CollaborationMode::Default;
                });
                rejects("plugin name", |value| {
                    value.invocations[0] = Invocation::Plugin(PluginInvocation::new(
                        "wrong",
                        "plugin://plugin@market",
                    ));
                });
                rejects("plugin URI", |value| {
                    value.invocations[0] =
                        Invocation::Plugin(PluginInvocation::new("plugin", "wrong"));
                });
                rejects("skill name", |value| {
                    value.invocations[1] =
                        Invocation::Skill(SkillInvocation::new("wrong", "skill.md"));
                });
                rejects("skill path", |value| {
                    value.invocations[1] =
                        Invocation::Skill(SkillInvocation::new("skill", "wrong"));
                });
                rejects("invocation order", |value| value.invocations.swap(0, 1));
                rejects("invocation kind", |value| {
                    value.invocations[0] =
                        Invocation::Skill(SkillInvocation::new("skill", "skill.md"));
                });
            },
        );
        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::send",
            "rust.conversation:011",
            || {
                let before = stable_strong_count(&conversation.inner);
                finish_retained(
                    &conversation.inner,
                    before,
                    conversation.send("héllo").unwrap(),
                )
                .unwrap();
                assert!(conversation.send("wrong-input").is_err());
                let failure = block_on(conversation.send("fail").unwrap()).unwrap_err();
                assert_eq!(failure.status, Status::OperationFailed);
                assert_eq!(failure.failure.unwrap().code, "mock.failure");
            },
        );

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::active_turn_progress",
            "rust.conversation:012",
            || {
                let before = stable_strong_count(&conversation.inner);
                let state = conversation.active_turn_progress().unwrap();
                assert!(Arc::strong_count(&conversation.inner) > before);
                assert_conversation_state(
                    &context,
                    state,
                    |value| {
                        value.as_ref().is_some_and(|value| {
                            value.text == "working"
                                && value.commentary == "commentary"
                                && value.reasoning == "reasoning"
                                && value.plan == "plan"
                                && value.plan_progress.is_none()
                                && value.shell_output == "output"
                                && value.shell_exit_code == Some(0)
                                && value.work_activity == Some(crate::WorkActivity::WritingFiles)
                                && value.hook_activities.is_empty()
                                && value.is_truncated
                        })
                    },
                    Option::is_none,
                );
                assert_eq!(stable_strong_count(&conversation.inner), before);
            },
        );
        for (index, symbol, test) in [
            (
                0,
                "codex_agent::CodexConversation::can_cancel_turn",
                "rust.conversation:013",
            ),
            (
                1,
                "codex_agent::CodexConversation::can_reload",
                "rust.conversation:014",
            ),
            (
                2,
                "codex_agent::CodexConversation::can_run_shell_command",
                "rust.conversation:015",
            ),
            (
                3,
                "codex_agent::CodexConversation::can_start_turn",
                "rust.conversation:016",
            ),
            (
                4,
                "codex_agent::CodexConversation::is_turn_active",
                "rust.conversation:018",
            ),
        ] {
            conversation_case(&mut executed, symbol, test, || {
                let before = stable_strong_count(&conversation.inner);
                let state = match index {
                    0 => conversation.can_cancel_turn(),
                    1 => conversation.can_reload(),
                    2 => conversation.can_run_shell_command(),
                    3 => conversation.can_start_turn(),
                    _ => conversation.is_turn_active(),
                }
                .unwrap();
                assert!(Arc::strong_count(&conversation.inner) > before);
                assert_conversation_state(&context, state, |value| *value, |value| !*value);
                assert_eq!(stable_strong_count(&conversation.inner), before);
            });
        }
        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::current_messages",
            "rust.conversation:017",
            || {
                let before = stable_strong_count(&conversation.inner);
                let state = conversation.current_messages().unwrap();
                assert!(Arc::strong_count(&conversation.inner) > before);
                assert_conversation_state(
                    &context,
                    state,
                    |values| {
                        exact_messages(values, "message-alpha", "message-beta");
                        true
                    },
                    |values| {
                        exact_messages(values, "message-gamma", "message-delta");
                        true
                    },
                );
                assert_eq!(stable_strong_count(&conversation.inner), before);
            },
        );
        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::state",
            "rust.conversation:019",
            || {
                let before = stable_strong_count(&conversation.inner);
                let state = conversation.state().unwrap();
                assert!(Arc::strong_count(&conversation.inner) > before);
                assert_conversation_state(
                    &context,
                    state,
                    |value| value.status == crate::ConversationStatus::Ready,
                    |value| value.status == crate::ConversationStatus::CancellingTurn,
                );
                assert_eq!(stable_strong_count(&conversation.inner), before);
            },
        );

        conversation_case(
            &mut executed,
            "codex_agent::CodexConversation::close",
            "rust.conversation:007",
            || {
                let before = stable_strong_count(&conversation.inner);
                finish_retained(&conversation.inner, before, conversation.close().unwrap())
                    .unwrap();
                let before = stable_strong_count(&conversation.inner);
                finish_retained(&conversation.inner, before, conversation.close().unwrap())
                    .unwrap();
            },
        );
        drop(retained_active);
        drop(conversation);
        drop(conversations);
        drop(agent);
        block_on(host.close().unwrap()).unwrap();
        drop(host);
        assert_eq!(executed.len(), 20);
        for index in 0..20 {
            assert!(executed.contains(&format!("rust.conversation:{index:03}")));
        }

        let cancel = exact_claim_calls(
            "codex_agent::CodexConversation::cancel_turn",
            "rust.conversation:006",
        );
        let reload = exact_claim_calls(
            "codex_agent::CodexConversation::reload",
            "rust.conversation:008",
        );
        assert!(
            validate_conversation_invocations(&cancel, &reload).is_err(),
            "wrong conversation method fails closed"
        );
        assert!(
            validate_conversation_invocations(
                &cancel,
                &BTreeSet::from(["codex_agent_removed_stale_trace".into()])
            )
            .is_err(),
            "stale trace fails closed"
        );
    }
}
