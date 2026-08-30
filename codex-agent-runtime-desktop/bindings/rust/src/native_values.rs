//! Owned decoders for stable C ABI value handles.

use crate::ffi;
use crate::{
    ApprovalPreset, AuthorizationPurpose, AuthorizationUrl, Capability, CatalogFreshness,
    ClientInfo, CodexError, CodexFailure, CodexNativeLibrary, CollaborationMode, Connector,
    ContextInner, ConversationId, ConversationSettings, ConversationSnapshot, ConversationSummary,
    Elicitation, ElicitationAction, ElicitationResponse, ElicitationValidation,
    ElicitationValidationIssue, ElicitationValidationReason, FormBoolean, FormField, FormNumber,
    FormOption, FormText, FormTextList, FormValue, HookActivity, HookRunStatus, InteractionState,
    Invocation, McpAuthStatus, McpAuthentication, McpEnvironmentSource, McpEnvironmentVariable,
    McpHttpTransport, McpOauthConfiguration, McpServer, McpServerConfiguration, McpStdioTransport,
    McpToolApproval, McpToolConfiguration, McpToolExposureSurface, McpTransport, Message,
    MessageRole, Model, PendingApproval, PendingElicitation, PendingInteraction, PlanProgress,
    PlanStep, PlanStepStatus, PluginAuthPolicy, PluginCatalog, PluginDetail, PluginInstallPolicy,
    PluginInstallResult, PluginInvocation, PluginReference, PluginSkill, PluginSummary,
    ResourceOrigin, ServiceTier, Skill, SkillCatalog, SkillChunk, SkillInvocation, SkillScope,
    Status, TurnProgress, TurnRequest, WorkActivity, Workspace, check, copy_string,
    quarantine_token, retry_cleanup,
};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

const MAX_COLLECTION_COUNT: usize = 1_000_000;

type Destroy<T> = unsafe extern "C" fn(*mut ffi::Context, *mut *mut T) -> i32;
type StringCopy<T> =
    unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut u8, usize, *mut usize) -> i32;
type ScalarI32<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32) -> i32;
type ScalarI64<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i64) -> i32;
type ScalarF64<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut f64) -> i32;
type OptionalI32<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32, *mut i32) -> i32;
type OptionalI64<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32, *mut i64) -> i32;
type OptionalF64<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut i32, *mut f64) -> i32;
type Count<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut usize) -> i32;
type StringAt<T> =
    unsafe extern "C" fn(*mut ffi::Context, *mut T, usize, *mut u8, usize, *mut usize) -> i32;
type Child<T, U> = unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut U) -> i32;
type ChildAt<T, U> = unsafe extern "C" fn(*mut ffi::Context, *mut T, usize, *mut *mut U) -> i32;
type ScalarAtI32<T> = unsafe extern "C" fn(*mut ffi::Context, *mut T, usize, *mut i32) -> i32;

pub(crate) fn symbol<T: Copy>(
    context: &Arc<ContextInner>,
    name: &'static [u8],
) -> Result<T, CodexError> {
    // SAFETY: every call site supplies the exact reviewed public C-header signature.
    unsafe { ffi::load_value_symbol(&context.library.api, name) }
        .map_err(|message| CodexError::new(Status::InternalError, message))
}

pub(crate) struct OwnedValue<'a, T> {
    context: &'a Arc<ContextInner>,
    raw: *mut T,
    destroy: Destroy<T>,
    resource: &'static str,
}

impl<'a, T> OwnedValue<'a, T> {
    pub(crate) fn new(
        context: &'a Arc<ContextInner>,
        raw: *mut T,
        destroy_name: &'static [u8],
        resource: &'static str,
    ) -> Result<Self, CodexError> {
        if raw.is_null() {
            return Err(CodexError::new(
                Status::InternalError,
                format!("native C SDK returned null {resource}"),
            ));
        }
        Ok(Self {
            context,
            raw,
            destroy: symbol(context, destroy_name)?,
            resource,
        })
    }

    pub(crate) fn raw(&self) -> *mut T {
        self.raw
    }

    pub(crate) fn close(mut self) -> Result<(), CodexError> {
        let (status, attempts) = retry_cleanup(|| {
            // SAFETY: raw is the unique transferred value handle in this local slot.
            unsafe { (self.destroy)(self.context.ptr(), &mut self.raw) }
        });
        if status == ffi::STATUS_OK {
            Ok(())
        } else {
            quarantine_token(
                self.context.clone(),
                self.raw as usize,
                self.resource,
                status,
                attempts,
            );
            self.raw = std::ptr::null_mut();
            Err(CodexError::new(
                Status::from_raw(status),
                format!("destroy native {}", self.resource),
            ))
        }
    }
}

pub(crate) fn create_owned<'a, T>(
    context: &'a Arc<ContextInner>,
    destroy_name: &'static [u8],
    resource: &'static str,
    create: impl FnOnce(*mut *mut T) -> i32,
) -> Result<OwnedValue<'a, T>, CodexError> {
    let mut raw = std::ptr::null_mut();
    check(create(&mut raw), resource)?;
    OwnedValue::new(context, raw, destroy_name, resource)
}

fn with_sync_context<T>(
    operation: impl FnOnce(&Arc<ContextInner>) -> Result<T, CodexError>,
) -> Result<T, CodexError> {
    let native = CodexNativeLibrary::load_default()?;
    let context = ContextInner::create(native.inner.clone())?;
    operation(&context)
}

impl<T> Drop for OwnedValue<'_, T> {
    fn drop(&mut self) {
        if self.raw.is_null() {
            return;
        }
        let (status, attempts) = retry_cleanup(|| {
            // SAFETY: raw is the unique transferred value handle in this local slot.
            unsafe { (self.destroy)(self.context.ptr(), &mut self.raw) }
        });
        if status != ffi::STATUS_OK {
            quarantine_token(
                self.context.clone(),
                self.raw as usize,
                self.resource,
                status,
                attempts,
            );
        }
        self.raw = std::ptr::null_mut();
    }
}

fn decode_owned<T, V>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    destroy: &'static [u8],
    resource: &'static str,
    decode: impl FnOnce(*mut T) -> Result<V, CodexError>,
) -> Result<V, CodexError> {
    let owned = OwnedValue::new(context, raw, destroy, resource)?;
    let result = decode(owned.raw());
    owned.close()?;
    result
}

fn string<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<String, CodexError> {
    let getter: StringCopy<T> = symbol(context, getter_name)?;
    copy_string(|buffer, capacity, required| {
        // SAFETY: raw is a live typed value and output follows the public copy contract.
        unsafe { getter(context.ptr(), raw, buffer, capacity, required) }
    })
}

fn i32_value<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<i32, CodexError> {
    let getter: ScalarI32<T> = symbol(context, getter_name)?;
    let mut value = 0;
    check(
        unsafe {
            // SAFETY: raw is live and value is a valid scalar output.
            getter(context.ptr(), raw, &mut value)
        },
        "read native value scalar",
    )?;
    Ok(value)
}

fn i64_value<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<i64, CodexError> {
    let getter: ScalarI64<T> = symbol(context, getter_name)?;
    let mut value = 0;
    check(
        unsafe {
            // SAFETY: raw is live and value is a valid scalar output.
            getter(context.ptr(), raw, &mut value)
        },
        "read native value scalar",
    )?;
    Ok(value)
}

fn f64_value<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<f64, CodexError> {
    let getter: ScalarF64<T> = symbol(context, getter_name)?;
    let mut value = 0.0;
    check(
        unsafe {
            // SAFETY: raw is live and value is a valid scalar output.
            getter(context.ptr(), raw, &mut value)
        },
        "read native f64 value",
    )?;
    if value.is_finite() {
        Ok(value)
    } else {
        Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned a non-finite f64",
        ))
    }
}

fn bool_value<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<bool, CodexError> {
    i32_value(context, raw, getter_name).and_then(|value| match value {
        0 => Ok(false),
        1 => Ok(true),
        _ => Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned a non-Boolean flag",
        )),
    })
}

fn optional_string<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    has_name: &'static [u8],
    copy_name: &'static [u8],
) -> Result<Option<String>, CodexError> {
    if bool_value(context, raw, has_name)? {
        string(context, raw, copy_name).map(Some)
    } else {
        Ok(None)
    }
}

fn optional_i32<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<Option<i32>, CodexError> {
    let getter: OptionalI32<T> = symbol(context, getter_name)?;
    let mut has = 0;
    let mut value = 0;
    check(
        unsafe {
            // SAFETY: raw is live and both scalar outputs are valid.
            getter(context.ptr(), raw, &mut has, &mut value)
        },
        "read optional native i32",
    )?;
    match has {
        0 => Ok(None),
        1 => Ok(Some(value)),
        _ => Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned an invalid presence flag",
        )),
    }
}

fn optional_i64<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<Option<i64>, CodexError> {
    let getter: OptionalI64<T> = symbol(context, getter_name)?;
    let mut has = 0;
    let mut value = 0;
    check(
        unsafe {
            // SAFETY: raw is live and both scalar outputs are valid.
            getter(context.ptr(), raw, &mut has, &mut value)
        },
        "read optional native i64",
    )?;
    match has {
        0 => Ok(None),
        1 => Ok(Some(value)),
        _ => Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned an invalid presence flag",
        )),
    }
}

fn optional_f64<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<Option<f64>, CodexError> {
    let getter: OptionalF64<T> = symbol(context, getter_name)?;
    let mut has = 0;
    let mut value = 0.0;
    check(
        unsafe {
            // SAFETY: raw is live and both scalar outputs are valid.
            getter(context.ptr(), raw, &mut has, &mut value)
        },
        "read optional native f64",
    )?;
    match has {
        0 => Ok(None),
        1 if value.is_finite() => Ok(Some(value)),
        1 => Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned a non-finite f64",
        )),
        _ => Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned an invalid presence flag",
        )),
    }
}

fn count<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<usize, CodexError> {
    let getter: Count<T> = symbol(context, getter_name)?;
    let mut value = 0;
    check(
        unsafe {
            // SAFETY: raw is live and value is a valid size output.
            getter(context.ptr(), raw, &mut value)
        },
        "read native collection count",
    )?;
    if value > MAX_COLLECTION_COUNT {
        return Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned an unreasonable collection count",
        ));
    }
    Ok(value)
}

fn strings<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    count_name: &'static [u8],
    copy_name: &'static [u8],
) -> Result<Vec<String>, CodexError> {
    let length = count(context, raw, count_name)?;
    let copy: StringAt<T> = symbol(context, copy_name)?;
    (0..length)
        .map(|index| {
            copy_string(|buffer, capacity, required| {
                // SAFETY: index is within the measured immutable list and outputs obey contract.
                unsafe { copy(context.ptr(), raw, index, buffer, capacity, required) }
            })
        })
        .collect()
}

fn optional_strings<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    has_name: &'static [u8],
    count_name: &'static [u8],
    copy_name: &'static [u8],
) -> Result<Option<Vec<String>>, CodexError> {
    if bool_value(context, raw, has_name)? {
        strings(context, raw, count_name, copy_name).map(Some)
    } else {
        Ok(None)
    }
}

fn string_map<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    count_name: &'static [u8],
    key_name: &'static [u8],
    value_name: &'static [u8],
) -> Result<BTreeMap<String, String>, CodexError> {
    let length = count(context, raw, count_name)?;
    let key: StringAt<T> = symbol(context, key_name)?;
    let value: StringAt<T> = symbol(context, value_name)?;
    let mut result = BTreeMap::new();
    for index in 0..length {
        let key = copy_string(|buffer, capacity, required| {
            // SAFETY: index is within the measured immutable map and outputs obey contract.
            unsafe { key(context.ptr(), raw, index, buffer, capacity, required) }
        })?;
        let value = copy_string(|buffer, capacity, required| {
            // SAFETY: index is within the measured immutable map and outputs obey contract.
            unsafe { value(context.ptr(), raw, index, buffer, capacity, required) }
        })?;
        if result.insert(key, value).is_some() {
            return Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a duplicate map key",
            ));
        }
    }
    Ok(result)
}

fn optional_string_map<T>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    has_name: &'static [u8],
    count_name: &'static [u8],
    key_name: &'static [u8],
    value_name: &'static [u8],
) -> Result<Option<BTreeMap<String, String>>, CodexError> {
    if bool_value(context, raw, has_name)? {
        string_map(context, raw, count_name, key_name, value_name).map(Some)
    } else {
        Ok(None)
    }
}

fn child<T, U>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
) -> Result<*mut U, CodexError> {
    let getter: Child<T, U> = symbol(context, getter_name)?;
    let mut value = std::ptr::null_mut();
    check(
        unsafe {
            // SAFETY: raw is live and value is an initially-null owned-child output slot.
            getter(context.ptr(), raw, &mut value)
        },
        "read native child value",
    )?;
    if value.is_null() {
        Err(CodexError::new(
            Status::InternalError,
            "native C SDK returned a null child value",
        ))
    } else {
        Ok(value)
    }
}

fn children<T, U, V>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    count_name: &'static [u8],
    at_name: &'static [u8],
    decode: fn(&Arc<ContextInner>, *mut U) -> Result<V, CodexError>,
) -> Result<Vec<V>, CodexError> {
    let length = count(context, raw, count_name)?;
    let at: ChildAt<T, U> = symbol(context, at_name)?;
    (0..length)
        .map(|index| {
            let mut value = std::ptr::null_mut();
            check(
                unsafe {
                    // SAFETY: index is within the measured immutable list; output starts null.
                    at(context.ptr(), raw, index, &mut value)
                },
                "read native child list value",
            )?;
            if value.is_null() {
                return Err(CodexError::new(
                    Status::InternalError,
                    "native C SDK returned a null child list value",
                ));
            }
            decode(context, value)
        })
        .collect()
}

fn enum_value<T, E>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
    convert: fn(i32) -> Option<E>,
) -> Result<E, CodexError> {
    convert(i32_value(context, raw, getter_name)?).ok_or_else(|| {
        CodexError::new(
            Status::InternalError,
            "native C SDK returned an unknown enum value",
        )
    })
}

fn optional_enum<T, E>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    getter_name: &'static [u8],
    convert: fn(i32) -> Option<E>,
) -> Result<Option<E>, CodexError> {
    optional_i32(context, raw, getter_name)?
        .map(|value| {
            convert(value).ok_or_else(|| {
                CodexError::new(
                    Status::InternalError,
                    "native C SDK returned an unknown optional enum value",
                )
            })
        })
        .transpose()
}

fn optional_enums<T, E>(
    context: &Arc<ContextInner>,
    raw: *mut T,
    has_name: &'static [u8],
    count_name: &'static [u8],
    at_name: &'static [u8],
    convert: fn(i32) -> Option<E>,
) -> Result<Option<Vec<E>>, CodexError> {
    if !bool_value(context, raw, has_name)? {
        return Ok(None);
    }
    let length = count(context, raw, count_name)?;
    let at: ScalarAtI32<T> = symbol(context, at_name)?;
    (0..length)
        .map(|index| {
            let mut value = 0;
            check(
                unsafe {
                    // SAFETY: index is within the measured immutable list and output is valid.
                    at(context.ptr(), raw, index, &mut value)
                },
                "read native enum list value",
            )?;
            convert(value).ok_or_else(|| {
                CodexError::new(
                    Status::InternalError,
                    "native C SDK returned an unknown enum list value",
                )
            })
        })
        .collect::<Result<Vec<_>, _>>()
        .map(Some)
}

pub(crate) fn decode_client_info(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ClientInfoValue,
) -> Result<ClientInfo, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_client_info_value_destroy\0",
        "client info value",
        |raw| {
            ClientInfo::new(
                string(context, raw, b"codex_agent_client_info_value_name_copy\0")?,
                string(context, raw, b"codex_agent_client_info_value_title_copy\0")?,
                string(
                    context,
                    raw,
                    b"codex_agent_client_info_value_version_copy\0",
                )?,
            )
        },
    )
}

pub(crate) fn decode_conversation_id(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ConversationId,
) -> Result<ConversationId, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_conversation_id_destroy\0",
        "conversation ID",
        |raw| {
            ConversationId::new(string(
                context,
                raw,
                b"codex_agent_conversation_id_value_copy\0",
            )?)
        },
    )
}

pub(crate) fn decode_workspace(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Workspace,
) -> Result<Workspace, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_workspace_destroy\0",
        "workspace value",
        |raw| {
            Workspace::new(
                string(context, raw, b"codex_agent_workspace_path_copy\0")?,
                Some(string(
                    context,
                    raw,
                    b"codex_agent_workspace_display_name_copy\0",
                )?),
            )
        },
    )
}

pub(crate) fn decode_conversation_settings(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ConversationSettings,
) -> Result<ConversationSettings, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_conversation_settings_destroy\0",
        "conversation settings",
        |raw| {
            Ok(ConversationSettings::new(
                enum_value(
                    context,
                    raw,
                    b"codex_agent_conversation_settings_approval_preset\0",
                    ApprovalPreset::from_raw,
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_conversation_settings_has_service_tier\0",
                    b"codex_agent_conversation_settings_service_tier_copy\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_conversation_summary(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ConversationSummary,
) -> Result<ConversationSummary, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_conversation_summary_destroy\0",
        "conversation summary",
        |raw| {
            Ok(ConversationSummary::new(
                decode_conversation_id(
                    context,
                    child(
                        context,
                        raw,
                        b"codex_agent_conversation_summary_conversation_id\0",
                    )?,
                )?,
                string(
                    context,
                    raw,
                    b"codex_agent_conversation_summary_title_copy\0",
                )?,
                i64_value(
                    context,
                    raw,
                    b"codex_agent_conversation_summary_updated_at_epoch_seconds\0",
                )?,
            ))
        },
    )
}

fn decode_invocation(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Invocation,
) -> Result<Invocation, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_invocation_destroy\0",
        "invocation",
        |raw| {
            type Kind =
                unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Invocation, *mut i32) -> i32;
            let kind: Kind = symbol(context, b"codex_agent_invocation_kind\0")?;
            let mut value = -1;
            check(
                // SAFETY: `raw` is an owned invocation from this context and `value` is writable.
                unsafe { kind(context.ptr(), raw, &mut value) },
                "read invocation kind",
            )?;
            match value {
                0 => {
                    let plugin: *mut ffi::InvocationPlugin =
                        child(context, raw, b"codex_agent_invocation_plugin\0")?;
                    decode_owned(
                        context,
                        plugin,
                        b"codex_agent_invocation_plugin_destroy\0",
                        "plugin invocation",
                        |plugin| {
                            Ok(Invocation::Plugin(PluginInvocation::new(
                                string(
                                    context,
                                    plugin,
                                    b"codex_agent_invocation_plugin_name_copy\0",
                                )?,
                                string(
                                    context,
                                    plugin,
                                    b"codex_agent_invocation_plugin_uri_copy\0",
                                )?,
                            )))
                        },
                    )
                }
                1 => {
                    let skill: *mut ffi::InvocationSkill =
                        child(context, raw, b"codex_agent_invocation_skill\0")?;
                    decode_owned(
                        context,
                        skill,
                        b"codex_agent_invocation_skill_destroy\0",
                        "skill invocation",
                        |skill| {
                            Ok(Invocation::Skill(SkillInvocation::new(
                                string(
                                    context,
                                    skill,
                                    b"codex_agent_invocation_skill_name_copy\0",
                                )?,
                                string(
                                    context,
                                    skill,
                                    b"codex_agent_invocation_skill_path_copy\0",
                                )?,
                            )))
                        },
                    )
                }
                _ => Err(CodexError::new(
                    Status::InternalError,
                    format!("unknown invocation kind {value}"),
                )),
            }
        },
    )
}

pub(crate) fn decode_message(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Message,
) -> Result<Message, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_message_destroy\0",
        "message",
        |raw| {
            let capability_count =
                count(context, raw, b"codex_agent_message_capabilities_count\0")?;
            type HasCapability =
                unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Message, i32, *mut i32) -> i32;
            let has_capability: HasCapability =
                symbol(context, b"codex_agent_message_has_capability\0")?;
            let mut capabilities = BTreeSet::new();
            let capability = Capability::WebSearch;
            let mut present = 0;
            check(
                // SAFETY: `raw` is a live message and `present` is writable for this exact query.
                unsafe { has_capability(context.ptr(), raw, capability as i32, &mut present) },
                "read message capability",
            )?;
            match present {
                0 => {}
                1 => {
                    capabilities.insert(capability);
                }
                _ => {
                    return Err(CodexError::new(
                        Status::InternalError,
                        "native C SDK returned an invalid capability flag",
                    ));
                }
            }
            if capabilities.len() != capability_count {
                return Err(CodexError::new(
                    Status::InternalError,
                    "native C SDK returned an unknown message capability",
                ));
            }
            Ok(Message::new(
                string(context, raw, b"codex_agent_message_id_copy\0")?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_message_has_client_message_id\0",
                    b"codex_agent_message_client_message_id_copy\0",
                )?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_message_role\0",
                    MessageRole::from_raw,
                )?,
                string(context, raw, b"codex_agent_message_text_copy\0")?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_message_collaboration_mode\0",
                    CollaborationMode::from_raw,
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_message_has_reasoning\0",
                    b"codex_agent_message_reasoning_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_message_has_plan\0",
                    b"codex_agent_message_plan_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_message_has_shell_command\0",
                    b"codex_agent_message_shell_command_copy\0",
                )?,
                optional_i32(context, raw, b"codex_agent_message_exit_code\0")?,
                capabilities,
                children(
                    context,
                    raw,
                    b"codex_agent_message_invocations_count\0",
                    b"codex_agent_message_invocation_at\0",
                    decode_invocation,
                )?,
            ))
        },
    )
}

pub(crate) fn decode_conversation_snapshot(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ConversationValue,
) -> Result<ConversationSnapshot, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_conversation_value_destroy\0",
        "conversation value",
        |raw| {
            Ok(ConversationSnapshot::new(
                decode_conversation_summary(
                    context,
                    child(context, raw, b"codex_agent_conversation_value_summary\0")?,
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_conversation_value_messages_count\0",
                    b"codex_agent_conversation_value_message_at\0",
                    decode_message,
                )?,
            ))
        },
    )
}

pub(crate) fn decode_form_option(
    context: &Arc<ContextInner>,
    raw: *mut ffi::FormOption,
) -> Result<FormOption, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_form_option_destroy\0",
        "form option",
        |raw| {
            Ok(FormOption::new(
                string(context, raw, b"codex_agent_form_option_value_copy\0")?,
                string(context, raw, b"codex_agent_form_option_title_copy\0")?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_form_option_has_description\0",
                    b"codex_agent_form_option_description_copy\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_mcp_environment_variable(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpEnvironmentVariable,
) -> Result<McpEnvironmentVariable, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_environment_variable_destroy\0",
        "MCP environment variable",
        |raw| {
            McpEnvironmentVariable::new(
                string(
                    context,
                    raw,
                    b"codex_agent_mcp_environment_variable_name_copy\0",
                )?,
                optional_enum(
                    context,
                    raw,
                    b"codex_agent_mcp_environment_variable_source\0",
                    McpEnvironmentSource::from_raw,
                )?,
            )
        },
    )
}

pub(crate) fn decode_mcp_oauth_configuration(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpOauthConfiguration,
) -> Result<McpOauthConfiguration, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_oauth_configuration_destroy\0",
        "MCP OAuth configuration",
        |raw| {
            McpOauthConfiguration::new(
                optional_string(
                    context,
                    raw,
                    b"codex_agent_mcp_oauth_configuration_has_client_id\0",
                    b"codex_agent_mcp_oauth_configuration_client_id_copy\0",
                )?,
                optional_i32(
                    context,
                    raw,
                    b"codex_agent_mcp_oauth_configuration_callback_port\0",
                )?,
            )
        },
    )
}

pub(crate) fn decode_mcp_tool_configuration(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpToolConfiguration,
) -> Result<McpToolConfiguration, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_tool_configuration_destroy\0",
        "MCP tool configuration",
        |raw| {
            Ok(McpToolConfiguration::new(optional_enum(
                context,
                raw,
                b"codex_agent_mcp_tool_configuration_approval\0",
                McpToolApproval::from_raw,
            )?))
        },
    )
}

pub(crate) fn decode_service_tier(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ServiceTier,
) -> Result<ServiceTier, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_service_tier_destroy\0",
        "service tier",
        |raw| {
            Ok(ServiceTier::new(
                string(context, raw, b"codex_agent_service_tier_id_copy\0")?,
                string(context, raw, b"codex_agent_service_tier_name_copy\0")?,
                string(context, raw, b"codex_agent_service_tier_description_copy\0")?,
            ))
        },
    )
}

pub(crate) fn decode_plan_step(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PlanStep,
) -> Result<PlanStep, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plan_step_destroy\0",
        "plan step",
        |raw| {
            Ok(PlanStep::new(
                string(context, raw, b"codex_agent_plan_step_text_copy\0")?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_plan_step_status\0",
                    PlanStepStatus::from_raw,
                )?,
            ))
        },
    )
}

pub(crate) fn decode_elicitation_validation_issue(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ElicitationValidationIssue,
) -> Result<ElicitationValidationIssue, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_elicitation_validation_issue_destroy\0",
        "elicitation validation issue",
        |raw| {
            Ok(ElicitationValidationIssue::new(
                string(
                    context,
                    raw,
                    b"codex_agent_elicitation_validation_issue_field_name_copy\0",
                )?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_elicitation_validation_issue_reason\0",
                    ElicitationValidationReason::from_raw,
                )?,
            ))
        },
    )
}

pub(crate) fn decode_hook_activity(
    context: &Arc<ContextInner>,
    raw: *mut ffi::HookActivity,
) -> Result<HookActivity, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_hook_activity_destroy\0",
        "hook activity",
        |raw| {
            Ok(HookActivity::new(
                string(context, raw, b"codex_agent_hook_activity_id_copy\0")?,
                string(context, raw, b"codex_agent_hook_activity_event_name_copy\0")?,
                string(
                    context,
                    raw,
                    b"codex_agent_hook_activity_handler_type_copy\0",
                )?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_hook_activity_status\0",
                    HookRunStatus::from_raw,
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_hook_activity_has_status_message\0",
                    b"codex_agent_hook_activity_status_message_copy\0",
                )?,
                strings(
                    context,
                    raw,
                    b"codex_agent_hook_activity_details_count\0",
                    b"codex_agent_hook_activity_detail_copy_at\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_plugin_reference(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PluginReference,
) -> Result<PluginReference, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plugin_reference_destroy\0",
        "plugin reference",
        |raw| {
            let value = PluginReference::new(
                string(context, raw, b"codex_agent_plugin_reference_id_copy\0")?,
                string(context, raw, b"codex_agent_plugin_reference_name_copy\0")?,
                string(
                    context,
                    raw,
                    b"codex_agent_plugin_reference_marketplace_name_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_reference_has_marketplace_path\0",
                    b"codex_agent_plugin_reference_marketplace_path_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_reference_has_remote_plugin_id\0",
                    b"codex_agent_plugin_reference_remote_plugin_id_copy\0",
                )?,
            );
            let native_uri = string(context, raw, b"codex_agent_plugin_reference_uri_copy\0")?;
            if native_uri != value.uri() {
                return Err(CodexError::new(
                    Status::InternalError,
                    "native plugin URI disagrees with canonical projection",
                ));
            }
            Ok(value)
        },
    )
}

pub(crate) fn decode_plugin_skill(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PluginSkill,
) -> Result<PluginSkill, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plugin_skill_destroy\0",
        "plugin skill",
        |raw| {
            Ok(PluginSkill::new(
                string(context, raw, b"codex_agent_plugin_skill_name_copy\0")?,
                string(context, raw, b"codex_agent_plugin_skill_description_copy\0")?,
                bool_value(context, raw, b"codex_agent_plugin_skill_is_enabled\0")?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_skill_has_path\0",
                    b"codex_agent_plugin_skill_path_copy\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_skill_chunk(
    context: &Arc<ContextInner>,
    raw: *mut ffi::SkillChunk,
) -> Result<SkillChunk, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_skill_chunk_destroy\0",
        "skill chunk",
        |raw| {
            Ok(SkillChunk::new(
                string(context, raw, b"codex_agent_skill_chunk_content_copy\0")?,
                optional_i64(context, raw, b"codex_agent_skill_chunk_next_offset\0")?,
                i64_value(context, raw, b"codex_agent_skill_chunk_total_bytes\0")?,
            ))
        },
    )
}

pub(crate) fn decode_failure_value(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Failure,
) -> Result<CodexFailure, CodexError> {
    crate::read_failure(context, raw)
}

pub(crate) fn decode_elicitation_validation(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ElicitationValidation,
) -> Result<ElicitationValidation, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_elicitation_validation_destroy\0",
        "elicitation validation",
        |raw| {
            let value = ElicitationValidation::new(children(
                context,
                raw,
                b"codex_agent_elicitation_validation_issue_count\0",
                b"codex_agent_elicitation_validation_issue_at\0",
                decode_elicitation_validation_issue,
            )?);
            let native_valid = bool_value(
                context,
                raw,
                b"codex_agent_elicitation_validation_is_valid\0",
            )?;
            if native_valid != value.is_valid() {
                return Err(CodexError::new(
                    Status::InternalError,
                    "native validation status disagrees with its issues",
                ));
            }
            Ok(value)
        },
    )
}

pub(crate) fn decode_plan_progress(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PlanProgress,
) -> Result<PlanProgress, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plan_progress_destroy\0",
        "plan progress",
        |raw| {
            Ok(PlanProgress::new(
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plan_progress_has_explanation\0",
                    b"codex_agent_plan_progress_explanation_copy\0",
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_plan_progress_steps_count\0",
                    b"codex_agent_plan_progress_step_at\0",
                    decode_plan_step,
                )?,
            ))
        },
    )
}

pub(crate) fn decode_model(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Model,
) -> Result<Model, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_model_destroy\0",
        "model",
        |raw| {
            Ok(Model::new(
                string(context, raw, b"codex_agent_model_id_copy\0")?,
                string(context, raw, b"codex_agent_model_display_name_copy\0")?,
                string(context, raw, b"codex_agent_model_description_copy\0")?,
                strings(
                    context,
                    raw,
                    b"codex_agent_model_supported_efforts_count\0",
                    b"codex_agent_model_supported_effort_copy_at\0",
                )?,
                string(context, raw, b"codex_agent_model_default_effort_copy\0")?,
                bool_value(context, raw, b"codex_agent_model_is_default\0")?,
                children(
                    context,
                    raw,
                    b"codex_agent_model_service_tiers_count\0",
                    b"codex_agent_model_service_tier_at\0",
                    decode_service_tier,
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_model_has_default_service_tier\0",
                    b"codex_agent_model_default_service_tier_copy\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_connector(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Connector,
) -> Result<Connector, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_connector_destroy\0",
        "connector",
        |raw| {
            Ok(Connector::new(
                string(context, raw, b"codex_agent_connector_id_copy\0")?,
                string(context, raw, b"codex_agent_connector_name_copy\0")?,
                string(context, raw, b"codex_agent_connector_description_copy\0")?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_connector_has_install_url\0",
                    b"codex_agent_connector_install_url_copy\0",
                )?,
                bool_value(context, raw, b"codex_agent_connector_is_accessible\0")?,
                bool_value(context, raw, b"codex_agent_connector_is_enabled\0")?,
                strings(
                    context,
                    raw,
                    b"codex_agent_connector_plugin_names_count\0",
                    b"codex_agent_connector_plugin_names_copy_at\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_plugin_summary(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PluginSummary,
) -> Result<PluginSummary, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plugin_summary_destroy\0",
        "plugin summary",
        |raw| {
            Ok(PluginSummary::new(
                decode_plugin_reference(
                    context,
                    child(context, raw, b"codex_agent_plugin_summary_reference\0")?,
                )?,
                string(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_display_name_copy\0",
                )?,
                string(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_description_copy\0",
                )?,
                bool_value(context, raw, b"codex_agent_plugin_summary_is_installed\0")?,
                bool_value(context, raw, b"codex_agent_plugin_summary_is_enabled\0")?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_install_policy\0",
                    PluginInstallPolicy::from_raw,
                )?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_auth_policy\0",
                    PluginAuthPolicy::from_raw,
                )?,
                bool_value(context, raw, b"codex_agent_plugin_summary_is_available\0")?,
                strings(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_capabilities_count\0",
                    b"codex_agent_plugin_summary_capabilities_copy_at\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_has_brand_color\0",
                    b"codex_agent_plugin_summary_brand_color_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_has_privacy_policy_url\0",
                    b"codex_agent_plugin_summary_privacy_policy_url_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_has_terms_of_service_url\0",
                    b"codex_agent_plugin_summary_terms_of_service_url_copy\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_summary_has_website_url\0",
                    b"codex_agent_plugin_summary_website_url_copy\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_plugin_catalog(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PluginCatalog,
) -> Result<PluginCatalog, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plugin_catalog_destroy\0",
        "plugin catalog",
        |raw| {
            Ok(PluginCatalog::new(
                children(
                    context,
                    raw,
                    b"codex_agent_plugin_catalog_plugins_count\0",
                    b"codex_agent_plugin_catalog_plugins_at\0",
                    decode_plugin_summary,
                )?,
                strings(
                    context,
                    raw,
                    b"codex_agent_plugin_catalog_errors_count\0",
                    b"codex_agent_plugin_catalog_errors_copy_at\0",
                )?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_plugin_catalog_freshness\0",
                    CatalogFreshness::from_raw,
                )?,
            ))
        },
    )
}

pub(crate) fn decode_plugin_detail(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PluginDetail,
) -> Result<PluginDetail, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plugin_detail_destroy\0",
        "plugin detail",
        |raw| {
            Ok(PluginDetail::new(
                decode_plugin_summary(
                    context,
                    child(context, raw, b"codex_agent_plugin_detail_summary\0")?,
                )?,
                string(
                    context,
                    raw,
                    b"codex_agent_plugin_detail_description_copy\0",
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_plugin_detail_skills_count\0",
                    b"codex_agent_plugin_detail_skills_at\0",
                    decode_plugin_skill,
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_plugin_detail_connectors_count\0",
                    b"codex_agent_plugin_detail_connectors_at\0",
                    decode_connector,
                )?,
                strings(
                    context,
                    raw,
                    b"codex_agent_plugin_detail_mcp_servers_count\0",
                    b"codex_agent_plugin_detail_mcp_servers_copy_at\0",
                )?,
                i32_value(context, raw, b"codex_agent_plugin_detail_hook_count\0")?,
            ))
        },
    )
}

pub(crate) fn decode_plugin_install_result(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PluginInstallResult,
) -> Result<PluginInstallResult, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_plugin_install_result_destroy\0",
        "plugin install result",
        |raw| {
            Ok(PluginInstallResult::new(
                enum_value(
                    context,
                    raw,
                    b"codex_agent_plugin_install_result_auth_policy\0",
                    PluginAuthPolicy::from_raw,
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_plugin_install_result_connectors_count\0",
                    b"codex_agent_plugin_install_result_connectors_at\0",
                    decode_connector,
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_plugin_install_result_has_message\0",
                    b"codex_agent_plugin_install_result_message_copy\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_skill(
    context: &Arc<ContextInner>,
    raw: *mut ffi::Skill,
) -> Result<Skill, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_skill_destroy\0",
        "skill",
        |raw| {
            Ok(Skill::new(
                string(context, raw, b"codex_agent_skill_name_copy\0")?,
                string(context, raw, b"codex_agent_skill_display_name_copy\0")?,
                string(context, raw, b"codex_agent_skill_description_copy\0")?,
                string(context, raw, b"codex_agent_skill_path_copy\0")?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_skill_scope\0",
                    SkillScope::from_raw,
                )?,
                bool_value(context, raw, b"codex_agent_skill_is_enabled\0")?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_skill_has_brand_color\0",
                    b"codex_agent_skill_brand_color_copy\0",
                )?,
                strings(
                    context,
                    raw,
                    b"codex_agent_skill_dependencies_count\0",
                    b"codex_agent_skill_dependencies_copy_at\0",
                )?,
                bool_value(context, raw, b"codex_agent_skill_can_uninstall\0")?,
                Some(enum_value(
                    context,
                    raw,
                    b"codex_agent_skill_origin\0",
                    ResourceOrigin::from_raw,
                )?),
            ))
        },
    )
}

pub(crate) fn decode_skill_catalog(
    context: &Arc<ContextInner>,
    raw: *mut ffi::SkillCatalog,
) -> Result<SkillCatalog, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_skill_catalog_destroy\0",
        "skill catalog",
        |raw| {
            Ok(SkillCatalog::new(
                children(
                    context,
                    raw,
                    b"codex_agent_skill_catalog_skills_count\0",
                    b"codex_agent_skill_catalog_skills_at\0",
                    decode_skill,
                )?,
                strings(
                    context,
                    raw,
                    b"codex_agent_skill_catalog_errors_count\0",
                    b"codex_agent_skill_catalog_errors_copy_at\0",
                )?,
            ))
        },
    )
}

pub(crate) fn decode_turn_progress(
    context: &Arc<ContextInner>,
    raw: *mut ffi::TurnProgress,
) -> Result<TurnProgress, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_turn_progress_destroy\0",
        "turn progress",
        |raw| {
            let plan_progress = if bool_value(
                context,
                raw,
                b"codex_agent_turn_progress_has_plan_progress\0",
            )? {
                Some(decode_plan_progress(
                    context,
                    child(context, raw, b"codex_agent_turn_progress_plan_progress\0")?,
                )?)
            } else {
                None
            };
            Ok(TurnProgress::new(
                string(context, raw, b"codex_agent_turn_progress_text_copy\0")?,
                string(context, raw, b"codex_agent_turn_progress_commentary_copy\0")?,
                string(context, raw, b"codex_agent_turn_progress_reasoning_copy\0")?,
                string(context, raw, b"codex_agent_turn_progress_plan_copy\0")?,
                plan_progress,
                string(
                    context,
                    raw,
                    b"codex_agent_turn_progress_shell_output_copy\0",
                )?,
                optional_i32(context, raw, b"codex_agent_turn_progress_shell_exit_code\0")?,
                optional_enum(
                    context,
                    raw,
                    b"codex_agent_turn_progress_work_activity\0",
                    WorkActivity::from_raw,
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_turn_progress_hook_activities_count\0",
                    b"codex_agent_turn_progress_hook_activity_at\0",
                    decode_hook_activity,
                )?,
                bool_value(context, raw, b"codex_agent_turn_progress_is_truncated\0")?,
            ))
        },
    )
}

pub(crate) fn decode_mcp_http_transport(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpTransportHttp,
) -> Result<McpHttpTransport, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_transport_http_destroy\0",
        "MCP HTTP transport",
        |raw| {
            McpHttpTransport::new(
                string(context, raw, b"codex_agent_mcp_transport_http_url_copy\0")?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_http_has_bearer_token_environment_variable\0",
                    b"codex_agent_mcp_transport_http_bearer_token_environment_variable_copy\0",
                )?,
                optional_string_map(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_http_has_headers\0",
                    b"codex_agent_mcp_transport_http_headers_count\0",
                    b"codex_agent_mcp_transport_http_headers_key_copy_at\0",
                    b"codex_agent_mcp_transport_http_headers_value_copy_at\0",
                )?,
                optional_string_map(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_http_has_environment_headers\0",
                    b"codex_agent_mcp_transport_http_environment_headers_count\0",
                    b"codex_agent_mcp_transport_http_environment_headers_key_copy_at\0",
                    b"codex_agent_mcp_transport_http_environment_headers_value_copy_at\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_http_has_headers_helper\0",
                    b"codex_agent_mcp_transport_http_headers_helper_copy\0",
                )?,
            )
        },
    )
}

pub(crate) fn decode_mcp_stdio_transport(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpTransportStdio,
) -> Result<McpStdioTransport, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_transport_stdio_destroy\0",
        "MCP stdio transport",
        |raw| {
            McpStdioTransport::new(
                string(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_stdio_command_copy\0",
                )?,
                strings(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_stdio_arguments_count\0",
                    b"codex_agent_mcp_transport_stdio_argument_copy_at\0",
                )?,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_stdio_has_working_directory\0",
                    b"codex_agent_mcp_transport_stdio_working_directory_copy\0",
                )?,
                optional_string_map(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_stdio_has_environment\0",
                    b"codex_agent_mcp_transport_stdio_environment_count\0",
                    b"codex_agent_mcp_transport_stdio_environment_key_copy_at\0",
                    b"codex_agent_mcp_transport_stdio_environment_value_copy_at\0",
                )?,
                children(
                    context,
                    raw,
                    b"codex_agent_mcp_transport_stdio_forwarded_environment_count\0",
                    b"codex_agent_mcp_transport_stdio_forwarded_environment_at\0",
                    decode_mcp_environment_variable,
                )?,
            )
        },
    )
}

pub(crate) fn decode_mcp_transport(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpTransport,
) -> Result<McpTransport, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_transport_destroy\0",
        "MCP transport",
        |raw| match i32_value(context, raw, b"codex_agent_mcp_transport_kind\0")? {
            0 => Ok(McpTransport::Http(decode_mcp_http_transport(
                context,
                child(context, raw, b"codex_agent_mcp_transport_http\0")?,
            )?)),
            1 => Ok(McpTransport::Stdio(decode_mcp_stdio_transport(
                context,
                child(context, raw, b"codex_agent_mcp_transport_stdio\0")?,
            )?)),
            _ => Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned an unknown MCP transport kind",
            )),
        },
    )
}

fn decode_mcp_tools(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpServerConfiguration,
) -> Result<BTreeMap<String, McpToolConfiguration>, CodexError> {
    let length = count(
        context,
        raw,
        b"codex_agent_mcp_server_configuration_tools_count\0",
    )?;
    let key: StringAt<ffi::McpServerConfiguration> = symbol(
        context,
        b"codex_agent_mcp_server_configuration_tools_key_copy_at\0",
    )?;
    let value: ChildAt<ffi::McpServerConfiguration, ffi::McpToolConfiguration> = symbol(
        context,
        b"codex_agent_mcp_server_configuration_tools_value_at\0",
    )?;
    let mut result = BTreeMap::new();
    for index in 0..length {
        let key = copy_string(|buffer, capacity, required| {
            // SAFETY: index is within the measured immutable map and outputs obey contract.
            unsafe { key(context.ptr(), raw, index, buffer, capacity, required) }
        })?;
        let mut child = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: index is within the measured immutable map and output starts null.
                value(context.ptr(), raw, index, &mut child)
            },
            "read native MCP tool configuration",
        )?;
        if child.is_null() {
            return Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a null MCP tool configuration",
            ));
        }
        let value = decode_mcp_tool_configuration(context, child)?;
        if result.insert(key, value).is_some() {
            return Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a duplicate MCP tool key",
            ));
        }
    }
    Ok(result)
}

pub(crate) fn decode_mcp_server_configuration(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpServerConfiguration,
) -> Result<McpServerConfiguration, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_server_configuration_destroy\0",
        "MCP server configuration",
        |raw| {
            let oauth = if bool_value(
                context,
                raw,
                b"codex_agent_mcp_server_configuration_has_oauth\0",
            )? {
                Some(decode_mcp_oauth_configuration(
                    context,
                    child(
                        context,
                        raw,
                        b"codex_agent_mcp_server_configuration_oauth\0",
                    )?,
                )?)
            } else {
                None
            };
            McpServerConfiguration::new(
                string(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_name_copy\0",
                )?,
                decode_mcp_transport(
                    context,
                    child(
                        context,
                        raw,
                        b"codex_agent_mcp_server_configuration_transport\0",
                    )?,
                )?,
                optional_enum(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_authentication\0",
                    McpAuthentication::from_raw,
                )?,
                string(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_environment_id_copy\0",
                )?,
                bool_value(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_is_enabled\0",
                )?,
                bool_value(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_is_required\0",
                )?,
                bool_value(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_supports_parallel_tool_calls\0",
                )?,
                optional_enums(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_has_omit_tools_from\0",
                    b"codex_agent_mcp_server_configuration_omit_tools_from_count\0",
                    b"codex_agent_mcp_server_configuration_omit_tools_from_at\0",
                    McpToolExposureSurface::from_raw,
                )?,
                optional_f64(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_startup_timeout_seconds\0",
                )?,
                optional_f64(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_tool_timeout_seconds\0",
                )?,
                optional_enum(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_default_tool_approval\0",
                    McpToolApproval::from_raw,
                )?,
                optional_strings(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_has_enabled_tools\0",
                    b"codex_agent_mcp_server_configuration_enabled_tools_count\0",
                    b"codex_agent_mcp_server_configuration_enabled_tool_copy_at\0",
                )?,
                optional_strings(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_has_disabled_tools\0",
                    b"codex_agent_mcp_server_configuration_disabled_tools_count\0",
                    b"codex_agent_mcp_server_configuration_disabled_tool_copy_at\0",
                )?,
                optional_strings(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_has_scopes\0",
                    b"codex_agent_mcp_server_configuration_scopes_count\0",
                    b"codex_agent_mcp_server_configuration_scope_copy_at\0",
                )?,
                oauth,
                optional_string(
                    context,
                    raw,
                    b"codex_agent_mcp_server_configuration_has_oauth_resource\0",
                    b"codex_agent_mcp_server_configuration_oauth_resource_copy\0",
                )?,
                decode_mcp_tools(context, raw)?,
            )
        },
    )
}

pub(crate) fn decode_mcp_server(
    context: &Arc<ContextInner>,
    raw: *mut ffi::McpServer,
) -> Result<McpServer, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_mcp_server_destroy\0",
        "MCP server",
        |raw| {
            let configuration =
                if bool_value(context, raw, b"codex_agent_mcp_server_has_configuration\0")? {
                    Some(decode_mcp_server_configuration(
                        context,
                        child(context, raw, b"codex_agent_mcp_server_configuration\0")?,
                    )?)
                } else {
                    None
                };
            let value = McpServer::new(
                string(context, raw, b"codex_agent_mcp_server_name_copy\0")?,
                string(context, raw, b"codex_agent_mcp_server_display_name_copy\0")?,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_mcp_server_auth_status\0",
                    McpAuthStatus::from_raw,
                )?,
                configuration,
                enum_value(
                    context,
                    raw,
                    b"codex_agent_mcp_server_origin\0",
                    ResourceOrigin::from_raw,
                )?,
                bool_value(context, raw, b"codex_agent_mcp_server_can_remove\0")?,
            );
            if value.is_authorized()
                != bool_value(context, raw, b"codex_agent_mcp_server_is_authorized\0")?
            {
                return Err(CodexError::new(
                    Status::InternalError,
                    "native C SDK returned inconsistent MCP authorization state",
                ));
            }
            Ok(value)
        },
    )
}

type CreateStringValue<T> =
    unsafe extern "C" fn(*mut ffi::Context, *const ffi::StringView, *mut *mut T) -> i32;
type CreateBooleanValue =
    unsafe extern "C" fn(*mut ffi::Context, i32, *mut *mut ffi::FormBooleanValue) -> i32;
type CreateNumberValue =
    unsafe extern "C" fn(*mut ffi::Context, f64, *mut *mut ffi::FormNumberValue) -> i32;
type CreateTextListValue = unsafe extern "C" fn(
    *mut ffi::Context,
    *const ffi::StringView,
    usize,
    *mut *mut ffi::FormTextListValue,
) -> i32;
type WrapFormValue<T> =
    unsafe extern "C" fn(*mut ffi::Context, *mut T, *mut *mut ffi::FormValue) -> i32;
type CreateFormOption = unsafe extern "C" fn(
    *mut ffi::Context,
    *const ffi::StringView,
    i32,
    *const ffi::StringView,
    i32,
    *const ffi::StringView,
    *mut *mut ffi::FormOption,
) -> i32;
type CreateFormField = unsafe extern "C" fn(
    *mut ffi::Context,
    *const ffi::StringView,
    *const ffi::StringView,
    i32,
    *const ffi::StringView,
    i32,
    i32,
    *const *mut ffi::FormOption,
    usize,
    i32,
    *mut ffi::FormValue,
    i32,
    f64,
    i32,
    f64,
    i32,
    i32,
    i32,
    i64,
    i32,
    i64,
    i32,
    i64,
    i32,
    i64,
    i32,
    i32,
    *mut *mut ffi::FormField,
) -> i32;
type CreateConversationId = CreateStringValue<ffi::ConversationId>;
type CreateElicitation = unsafe extern "C" fn(
    *mut ffi::Context,
    *const ffi::StringView,
    *const ffi::StringView,
    *mut ffi::ConversationId,
    *const ffi::StringView,
    i32,
    *const *mut ffi::FormField,
    usize,
    i32,
    *const ffi::StringView,
    *mut *mut ffi::Elicitation,
) -> i32;
type CreateFormContent = unsafe extern "C" fn(
    *mut ffi::Context,
    *const ffi::StringView,
    *const *mut ffi::FormValue,
    usize,
    *mut *mut ffi::FormContent,
) -> i32;
type CreateElicitationResponse = unsafe extern "C" fn(
    *mut ffi::Context,
    i32,
    *const ffi::StringView,
    *const *mut ffi::FormValue,
    usize,
    *mut *mut ffi::ElicitationResponse,
) -> i32;

fn flag(value: bool) -> i32 {
    i32::from(value)
}

fn exact_array<T>(values: &[T]) -> *const T {
    if values.is_empty() {
        std::ptr::null()
    } else {
        values.as_ptr()
    }
}

fn optional_f64_input(value: Option<f64>) -> (i32, f64) {
    value.map_or((0, 0.0), |value| (1, value))
}

fn optional_i64_input(value: Option<i64>) -> (i32, i64) {
    value.map_or((0, 0), |value| (1, value))
}

fn encode_form_value<'a>(
    context: &'a Arc<ContextInner>,
    value: &FormValue,
) -> Result<OwnedValue<'a, ffi::FormValue>, CodexError> {
    match value {
        FormValue::Boolean(value) => {
            let create: CreateBooleanValue =
                symbol(context, b"codex_agent_form_boolean_value_create\0")?;
            let carrier = create_owned(
                context,
                b"codex_agent_form_boolean_value_destroy\0",
                "form Boolean value",
                |out| unsafe {
                    // SAFETY: the live context and initially-null typed output obey the C ABI.
                    create(context.ptr(), flag(value.value), out)
                },
            )?;
            let wrap: WrapFormValue<ffi::FormBooleanValue> =
                symbol(context, b"codex_agent_form_value_from_boolean\0")?;
            create_owned(
                context,
                b"codex_agent_form_value_destroy\0",
                "form value",
                |out| unsafe {
                    // SAFETY: carrier is a live same-context typed value copied by the C ABI.
                    wrap(context.ptr(), carrier.raw(), out)
                },
            )
        }
        FormValue::Number(value) => {
            let create: CreateNumberValue =
                symbol(context, b"codex_agent_form_number_value_create\0")?;
            let carrier = create_owned(
                context,
                b"codex_agent_form_number_value_destroy\0",
                "form number value",
                |out| unsafe {
                    // SAFETY: the live context and initially-null typed output obey the C ABI.
                    create(context.ptr(), value.value, out)
                },
            )?;
            let wrap: WrapFormValue<ffi::FormNumberValue> =
                symbol(context, b"codex_agent_form_value_from_number\0")?;
            create_owned(
                context,
                b"codex_agent_form_value_destroy\0",
                "form value",
                |out| unsafe {
                    // SAFETY: carrier is a live same-context typed value copied by the C ABI.
                    wrap(context.ptr(), carrier.raw(), out)
                },
            )
        }
        FormValue::Text(value) => {
            let create: CreateStringValue<ffi::FormTextValue> =
                symbol(context, b"codex_agent_form_text_value_create\0")?;
            let view = ffi::StringView::new(&value.value);
            let carrier = create_owned(
                context,
                b"codex_agent_form_text_value_destroy\0",
                "form text value",
                |out| unsafe {
                    // SAFETY: view borrows value through this copying call only.
                    create(context.ptr(), &view, out)
                },
            )?;
            let wrap: WrapFormValue<ffi::FormTextValue> =
                symbol(context, b"codex_agent_form_value_from_text\0")?;
            create_owned(
                context,
                b"codex_agent_form_value_destroy\0",
                "form value",
                |out| unsafe {
                    // SAFETY: carrier is a live same-context typed value copied by the C ABI.
                    wrap(context.ptr(), carrier.raw(), out)
                },
            )
        }
        FormValue::TextList(value) => {
            let create: CreateTextListValue =
                symbol(context, b"codex_agent_form_text_list_value_create\0")?;
            let views = value
                .value
                .iter()
                .map(|item| ffi::StringView::new(item))
                .collect::<Vec<_>>();
            let carrier = create_owned(
                context,
                b"codex_agent_form_text_list_value_destroy\0",
                "form text-list value",
                |out| unsafe {
                    // SAFETY: every view remains borrowed through this copying call.
                    create(context.ptr(), exact_array(&views), views.len(), out)
                },
            )?;
            let wrap: WrapFormValue<ffi::FormTextListValue> =
                symbol(context, b"codex_agent_form_value_from_text_list\0")?;
            create_owned(
                context,
                b"codex_agent_form_value_destroy\0",
                "form value",
                |out| unsafe {
                    // SAFETY: carrier is a live same-context typed value copied by the C ABI.
                    wrap(context.ptr(), carrier.raw(), out)
                },
            )
        }
    }
}

pub(crate) fn decode_form_value(
    context: &Arc<ContextInner>,
    raw: *mut ffi::FormValue,
) -> Result<FormValue, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_form_value_destroy\0",
        "form value",
        |raw| match i32_value(context, raw, b"codex_agent_form_value_kind\0")? {
            0 => decode_owned(
                context,
                child::<ffi::FormValue, ffi::FormBooleanValue>(
                    context,
                    raw,
                    b"codex_agent_form_value_boolean\0",
                )?,
                b"codex_agent_form_boolean_value_destroy\0",
                "form Boolean value",
                |carrier| {
                    Ok(FormValue::Boolean(FormBoolean::new(bool_value(
                        context,
                        carrier,
                        b"codex_agent_form_boolean_value_value\0",
                    )?)))
                },
            ),
            1 => decode_owned(
                context,
                child::<ffi::FormValue, ffi::FormNumberValue>(
                    context,
                    raw,
                    b"codex_agent_form_value_number\0",
                )?,
                b"codex_agent_form_number_value_destroy\0",
                "form number value",
                |carrier| {
                    Ok(FormValue::Number(FormNumber::new(f64_value(
                        context,
                        carrier,
                        b"codex_agent_form_number_value_value\0",
                    )?)?))
                },
            ),
            2 => decode_owned(
                context,
                child::<ffi::FormValue, ffi::FormTextValue>(
                    context,
                    raw,
                    b"codex_agent_form_value_text\0",
                )?,
                b"codex_agent_form_text_value_destroy\0",
                "form text value",
                |carrier| {
                    Ok(FormValue::Text(FormText::new(string(
                        context,
                        carrier,
                        b"codex_agent_form_text_value_value_copy\0",
                    )?)))
                },
            ),
            3 => decode_owned(
                context,
                child::<ffi::FormValue, ffi::FormTextListValue>(
                    context,
                    raw,
                    b"codex_agent_form_value_text_list\0",
                )?,
                b"codex_agent_form_text_list_value_destroy\0",
                "form text-list value",
                |carrier| {
                    Ok(FormValue::TextList(FormTextList::new(strings(
                        context,
                        carrier,
                        b"codex_agent_form_text_list_value_count\0",
                        b"codex_agent_form_text_list_value_copy_at\0",
                    )?)))
                },
            ),
            _ => Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned an unknown form-value kind",
            )),
        },
    )
}

fn encode_form_option<'a>(
    context: &'a Arc<ContextInner>,
    option: &FormOption,
) -> Result<OwnedValue<'a, ffi::FormOption>, CodexError> {
    let create: CreateFormOption = symbol(context, b"codex_agent_form_option_create\0")?;
    let value = ffi::StringView::new(&option.value);
    let title = ffi::StringView::new(&option.title);
    let description = option
        .description
        .as_deref()
        .map(ffi::StringView::new)
        .unwrap_or_else(ffi::StringView::absent);
    create_owned(
        context,
        b"codex_agent_form_option_destroy\0",
        "form option",
        |out| unsafe {
            // SAFETY: views and the initially-null output remain live through this copying call.
            create(
                context.ptr(),
                &value,
                1,
                &title,
                flag(option.description.is_some()),
                &description,
                out,
            )
        },
    )
}

fn encode_form_field<'a>(
    context: &'a Arc<ContextInner>,
    field: &FormField,
) -> Result<OwnedValue<'a, ffi::FormField>, CodexError> {
    let options = field
        .options
        .iter()
        .map(|option| encode_form_option(context, option))
        .collect::<Result<Vec<_>, _>>()?;
    let option_raw = options.iter().map(OwnedValue::raw).collect::<Vec<_>>();
    let default_value = field
        .default_value
        .as_ref()
        .map(|value| encode_form_value(context, value))
        .transpose()?;
    let create: CreateFormField = symbol(context, b"codex_agent_form_field_create\0")?;
    let name = ffi::StringView::new(&field.name);
    let title = ffi::StringView::new(&field.title);
    let description = field
        .description
        .as_deref()
        .map(ffi::StringView::new)
        .unwrap_or_else(ffi::StringView::absent);
    let (has_minimum, minimum) = optional_f64_input(field.minimum);
    let (has_maximum, maximum) = optional_f64_input(field.maximum);
    let (has_minimum_length, minimum_length) = optional_i64_input(field.minimum_length);
    let (has_maximum_length, maximum_length) = optional_i64_input(field.maximum_length);
    let (has_minimum_selections, minimum_selections) = optional_i64_input(field.minimum_selections);
    let (has_maximum_selections, maximum_selections) = optional_i64_input(field.maximum_selections);
    create_owned(
        context,
        b"codex_agent_form_field_destroy\0",
        "form field",
        |out| unsafe {
            // SAFETY: all nested handles and borrowed views remain live through this copying call.
            create(
                context.ptr(),
                &name,
                &title,
                flag(field.description.is_some()),
                &description,
                flag(field.is_required),
                field.field_type as i32,
                exact_array(&option_raw),
                option_raw.len(),
                flag(default_value.is_some()),
                default_value
                    .as_ref()
                    .map_or(std::ptr::null_mut(), OwnedValue::raw),
                has_minimum,
                minimum,
                has_maximum,
                maximum,
                flag(field.format.is_some()),
                field.format.map_or(0, |value| value as i32),
                has_minimum_length,
                minimum_length,
                has_maximum_length,
                maximum_length,
                has_minimum_selections,
                minimum_selections,
                has_maximum_selections,
                maximum_selections,
                flag(field.allows_other),
                flag(field.is_secret),
                out,
            )
        },
    )
}

pub(crate) fn encode_conversation_id<'a>(
    context: &'a Arc<ContextInner>,
    value: &ConversationId,
) -> Result<OwnedValue<'a, ffi::ConversationId>, CodexError> {
    let create: CreateConversationId = symbol(context, b"codex_agent_conversation_id_create\0")?;
    let view = ffi::StringView::new(&value.value);
    create_owned(
        context,
        b"codex_agent_conversation_id_destroy\0",
        "conversation ID",
        |out| unsafe {
            // SAFETY: view remains borrowed through this copying call.
            create(context.ptr(), &view, out)
        },
    )
}

fn encode_invocation<'a>(
    context: &'a Arc<ContextInner>,
    value: &Invocation,
) -> Result<OwnedValue<'a, ffi::Invocation>, CodexError> {
    type FromPlugin = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::InvocationPlugin,
        *mut *mut ffi::Invocation,
    ) -> i32;
    type FromSkill = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::InvocationSkill,
        *mut *mut ffi::Invocation,
    ) -> i32;
    match value {
        Invocation::Plugin(value) => {
            type Create = unsafe extern "C" fn(
                *mut ffi::Context,
                *const ffi::StringView,
                *const ffi::StringView,
                *mut *mut ffi::InvocationPlugin,
            ) -> i32;
            let name = ffi::StringView::new(&value.name);
            let uri = ffi::StringView::new(&value.uri);
            let create: Create = symbol(context, b"codex_agent_invocation_plugin_create\0")?;
            let plugin = create_owned(
                context,
                b"codex_agent_invocation_plugin_destroy\0",
                "plugin invocation",
                // SAFETY: views borrow live Rust strings and `out` is writable for this call.
                |out| unsafe { create(context.ptr(), &name, &uri, out) },
            )?;
            let wrap: FromPlugin = symbol(context, b"codex_agent_invocation_from_plugin\0")?;
            create_owned(
                context,
                b"codex_agent_invocation_destroy\0",
                "invocation",
                // SAFETY: `plugin` remains owned until the wrapper call returns and `out` is writable.
                |out| unsafe { wrap(context.ptr(), plugin.raw(), out) },
            )
        }
        Invocation::Skill(value) => {
            type Create = unsafe extern "C" fn(
                *mut ffi::Context,
                *const ffi::StringView,
                *const ffi::StringView,
                *mut *mut ffi::InvocationSkill,
            ) -> i32;
            let name = ffi::StringView::new(&value.name);
            let path = ffi::StringView::new(&value.path);
            let create: Create = symbol(context, b"codex_agent_invocation_skill_create\0")?;
            let skill = create_owned(
                context,
                b"codex_agent_invocation_skill_destroy\0",
                "skill invocation",
                // SAFETY: views borrow live Rust strings and `out` is writable for this call.
                |out| unsafe { create(context.ptr(), &name, &path, out) },
            )?;
            let wrap: FromSkill = symbol(context, b"codex_agent_invocation_from_skill\0")?;
            create_owned(
                context,
                b"codex_agent_invocation_destroy\0",
                "invocation",
                // SAFETY: `skill` remains owned until the wrapper call returns and `out` is writable.
                |out| unsafe { wrap(context.ptr(), skill.raw(), out) },
            )
        }
    }
}

pub(crate) fn encode_turn_request<'a>(
    context: &'a Arc<ContextInner>,
    value: &TurnRequest,
) -> Result<OwnedValue<'a, ffi::TurnRequest>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const ffi::StringView,
        i32,
        *const i32,
        usize,
        *const *mut ffi::Invocation,
        usize,
        i32,
        *mut *mut ffi::TurnRequest,
    ) -> i32;
    let prompt = ffi::StringView::new(&value.prompt);
    let client_message_id = value
        .client_message_id
        .as_deref()
        .map_or_else(ffi::StringView::absent, ffi::StringView::new);
    let model = value
        .model
        .as_deref()
        .map_or_else(ffi::StringView::absent, ffi::StringView::new);
    let effort = value
        .effort
        .as_deref()
        .map_or_else(ffi::StringView::absent, ffi::StringView::new);
    let service_tier = value
        .service_tier
        .as_deref()
        .map_or_else(ffi::StringView::absent, ffi::StringView::new);
    let capabilities = value
        .capabilities
        .iter()
        .map(|capability| *capability as i32)
        .collect::<Vec<_>>();
    let invocations = value
        .invocations
        .iter()
        .map(|invocation| encode_invocation(context, invocation))
        .collect::<Result<Vec<_>, _>>()?;
    let invocation_raw = invocations.iter().map(OwnedValue::raw).collect::<Vec<_>>();
    let create: Create = symbol(context, b"codex_agent_turn_request_create\0")?;
    create_owned(
        context,
        b"codex_agent_turn_request_destroy\0",
        "turn request",
        // SAFETY: all views and encoded child handles remain live through the synchronous create call.
        |out| unsafe {
            create(
                context.ptr(),
                &prompt,
                flag(value.client_message_id.is_some()),
                &client_message_id,
                flag(value.model.is_some()),
                &model,
                flag(value.effort.is_some()),
                &effort,
                flag(value.service_tier.is_some()),
                &service_tier,
                value.approval_preset.raw(),
                exact_array(&capabilities),
                capabilities.len(),
                exact_array(&invocation_raw),
                invocation_raw.len(),
                value.collaboration_mode as i32,
                out,
            )
        },
    )
}

fn encode_elicitation<'a>(
    context: &'a Arc<ContextInner>,
    elicitation: &Elicitation,
) -> Result<OwnedValue<'a, ffi::Elicitation>, CodexError> {
    let conversation_id = encode_conversation_id(context, &elicitation.conversation_id)?;
    let form = elicitation
        .form
        .as_deref()
        .unwrap_or_default()
        .iter()
        .map(|field| encode_form_field(context, field))
        .collect::<Result<Vec<_>, _>>()?;
    let form_raw = form.iter().map(OwnedValue::raw).collect::<Vec<_>>();
    let create: CreateElicitation = symbol(context, b"codex_agent_elicitation_create\0")?;
    let request_id = ffi::StringView::new(&elicitation.request_id);
    let server_name = ffi::StringView::new(&elicitation.server_name);
    let message = ffi::StringView::new(&elicitation.message);
    let url = elicitation
        .url
        .as_deref()
        .map(ffi::StringView::new)
        .unwrap_or_else(ffi::StringView::absent);
    create_owned(
        context,
        b"codex_agent_elicitation_destroy\0",
        "elicitation",
        |out| unsafe {
            // SAFETY: every nested handle and view remains live through this copying call.
            create(
                context.ptr(),
                &request_id,
                &server_name,
                conversation_id.raw(),
                &message,
                flag(elicitation.form.is_some()),
                exact_array(&form_raw),
                form_raw.len(),
                flag(elicitation.url.is_some()),
                &url,
                out,
            )
        },
    )
}

fn encode_form_content<'a>(
    context: &'a Arc<ContextInner>,
    content: &BTreeMap<String, FormValue>,
) -> Result<OwnedValue<'a, ffi::FormContent>, CodexError> {
    let keys = content
        .keys()
        .map(|key| ffi::StringView::new(key))
        .collect::<Vec<_>>();
    let values = content
        .values()
        .map(|value| encode_form_value(context, value))
        .collect::<Result<Vec<_>, _>>()?;
    let raw_values = values.iter().map(OwnedValue::raw).collect::<Vec<_>>();
    let create: CreateFormContent = symbol(context, b"codex_agent_form_content_create\0")?;
    create_owned(
        context,
        b"codex_agent_form_content_destroy\0",
        "form content",
        |out| unsafe {
            // SAFETY: key views and nested values remain live through this copying call.
            create(
                context.ptr(),
                exact_array(&keys),
                exact_array(&raw_values),
                raw_values.len(),
                out,
            )
        },
    )
}

fn decode_form_content(
    context: &Arc<ContextInner>,
    raw: *mut ffi::FormContent,
) -> Result<BTreeMap<String, FormValue>, CodexError> {
    type ValueAt = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::FormContent,
        *const ffi::StringView,
        *mut *mut ffi::FormValue,
    ) -> i32;
    decode_owned(
        context,
        raw,
        b"codex_agent_form_content_destroy\0",
        "form content",
        |raw| {
            let length = count(context, raw, b"codex_agent_form_content_count\0")?;
            let key_at: StringAt<ffi::FormContent> =
                symbol(context, b"codex_agent_form_content_key_copy\0")?;
            let value_at: ValueAt = symbol(context, b"codex_agent_form_content_value_at\0")?;
            let mut content = BTreeMap::new();
            for index in 0..length {
                let key = copy_string(|buffer, capacity, required| unsafe {
                    // SAFETY: index is within the measured immutable map.
                    key_at(context.ptr(), raw, index, buffer, capacity, required)
                })?;
                let view = ffi::StringView::new(&key);
                let mut value = std::ptr::null_mut();
                check(
                    unsafe {
                        // SAFETY: view and initially-null typed output follow the public contract.
                        value_at(context.ptr(), raw, &view, &mut value)
                    },
                    "read native form-content value",
                )?;
                let value = decode_form_value(context, value)?;
                if content.insert(key, value).is_some() {
                    return Err(CodexError::new(
                        Status::InternalError,
                        "native C SDK returned a duplicate form-content key",
                    ));
                }
            }
            Ok(content)
        },
    )
}

pub(crate) fn encode_elicitation_response<'a>(
    context: &'a Arc<ContextInner>,
    response: &ElicitationResponse,
) -> Result<OwnedValue<'a, ffi::ElicitationResponse>, CodexError> {
    let keys = response
        .content
        .keys()
        .map(|key| ffi::StringView::new(key))
        .collect::<Vec<_>>();
    let values = response
        .content
        .values()
        .map(|value| encode_form_value(context, value))
        .collect::<Result<Vec<_>, _>>()?;
    let raw_values = values.iter().map(OwnedValue::raw).collect::<Vec<_>>();
    let create: CreateElicitationResponse =
        symbol(context, b"codex_agent_elicitation_response_create\0")?;
    create_owned(
        context,
        b"codex_agent_elicitation_response_destroy\0",
        "elicitation response",
        |out| unsafe {
            // SAFETY: key views and nested values remain live through this copying call.
            create(
                context.ptr(),
                response.action as i32,
                exact_array(&keys),
                exact_array(&raw_values),
                raw_values.len(),
                out,
            )
        },
    )
}

fn decode_elicitation_response(
    context: &Arc<ContextInner>,
    raw: *mut ffi::ElicitationResponse,
    expected_keys: impl IntoIterator<Item = String>,
) -> Result<ElicitationResponse, CodexError> {
    type ContentValue = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::ElicitationResponse,
        *const ffi::StringView,
        *mut *mut ffi::FormValue,
    ) -> i32;
    decode_owned(
        context,
        raw,
        b"codex_agent_elicitation_response_destroy\0",
        "elicitation response",
        |raw| {
            let action = ElicitationAction::from_raw(i32_value(
                context,
                raw,
                b"codex_agent_elicitation_response_action\0",
            )?)
            .ok_or_else(|| {
                CodexError::new(
                    Status::InternalError,
                    "native C SDK returned an unknown elicitation action",
                )
            })?;
            let expected_keys = expected_keys.into_iter().collect::<Vec<_>>();
            if count(
                context,
                raw,
                b"codex_agent_elicitation_response_content_count\0",
            )? != expected_keys.len()
            {
                return Err(CodexError::new(
                    Status::InternalError,
                    "native C SDK returned an unexpected elicitation-response shape",
                ));
            }
            let value_at: ContentValue =
                symbol(context, b"codex_agent_elicitation_response_content_value\0")?;
            let mut content = BTreeMap::new();
            for key in expected_keys {
                let view = ffi::StringView::new(&key);
                let mut value = std::ptr::null_mut();
                check(
                    unsafe {
                        // SAFETY: view and initially-null typed output follow the public contract.
                        value_at(context.ptr(), raw, &view, &mut value)
                    },
                    "read native elicitation-response value",
                )?;
                content.insert(key, decode_form_value(context, value)?);
            }
            Ok(ElicitationResponse::new(action, content))
        },
    )
}

pub(crate) fn sync_authorization_url_chat_gpt(value: &str) -> Result<AuthorizationUrl, CodexError> {
    with_sync_context(|context| {
        type Factory = unsafe extern "C" fn(
            *mut ffi::Context,
            *const ffi::StringView,
            *mut *mut ffi::AuthorizationUrl,
        ) -> i32;
        let codex_agent_authorization_url_chat_gpt: Factory =
            symbol(context, b"codex_agent_authorization_url_chat_gpt\0")?;
        let view = ffi::StringView::new(value);
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: view and initially-null typed output follow the exact public C ABI.
                codex_agent_authorization_url_chat_gpt(context.ptr(), &view, &mut raw)
            },
            "create ChatGPT authorization URL",
        )?;
        decode_authorization_url(context, raw)
    })
}

pub(crate) fn sync_authorization_url_external(value: &str) -> Result<AuthorizationUrl, CodexError> {
    with_sync_context(|context| {
        type Factory = unsafe extern "C" fn(
            *mut ffi::Context,
            *const ffi::StringView,
            *mut *mut ffi::AuthorizationUrl,
        ) -> i32;
        let codex_agent_authorization_url_external: Factory =
            symbol(context, b"codex_agent_authorization_url_external\0")?;
        let view = ffi::StringView::new(value);
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: view and initially-null typed output follow the exact public C ABI.
                codex_agent_authorization_url_external(context.ptr(), &view, &mut raw)
            },
            "create external authorization URL",
        )?;
        decode_authorization_url(context, raw)
    })
}

fn decode_authorization_url(
    context: &Arc<ContextInner>,
    raw: *mut ffi::AuthorizationUrl,
) -> Result<AuthorizationUrl, CodexError> {
    decode_owned(
        context,
        raw,
        b"codex_agent_authorization_url_destroy\0",
        "authorization URL",
        |raw| {
            let purpose = AuthorizationPurpose::from_raw(i32_value(
                context,
                raw,
                b"codex_agent_authorization_url_purpose\0",
            )?)
            .ok_or_else(|| {
                CodexError::new(
                    Status::InternalError,
                    "native C SDK returned an unknown authorization purpose",
                )
            })?;
            Ok(AuthorizationUrl {
                value: string(context, raw, b"codex_agent_authorization_url_value_copy\0")?,
                purpose,
            })
        },
    )
}

pub(crate) fn sync_elicitation_response_decline() -> Result<ElicitationResponse, CodexError> {
    with_sync_context(|context| {
        type Factory =
            unsafe extern "C" fn(*mut ffi::Context, *mut *mut ffi::ElicitationResponse) -> i32;
        let codex_agent_elicitation_response_decline: Factory =
            symbol(context, b"codex_agent_elicitation_response_decline\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: raw is an initially-null typed output for the exact public C ABI.
                codex_agent_elicitation_response_decline(context.ptr(), &mut raw)
            },
            "create declined elicitation response",
        )?;
        decode_elicitation_response(context, raw, std::iter::empty())
    })
}

pub(crate) fn sync_elicitation_response_cancel() -> Result<ElicitationResponse, CodexError> {
    with_sync_context(|context| {
        type Factory =
            unsafe extern "C" fn(*mut ffi::Context, *mut *mut ffi::ElicitationResponse) -> i32;
        let codex_agent_elicitation_response_cancel: Factory =
            symbol(context, b"codex_agent_elicitation_response_cancel\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: raw is an initially-null typed output for the exact public C ABI.
                codex_agent_elicitation_response_cancel(context.ptr(), &mut raw)
            },
            "create cancelled elicitation response",
        )?;
        decode_elicitation_response(context, raw, std::iter::empty())
    })
}

pub(crate) fn sync_form_field_accepts(
    field: &FormField,
    value: Option<&FormValue>,
) -> Result<bool, CodexError> {
    with_sync_context(|context| {
        type Accepts = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::FormField,
            *mut ffi::FormValue,
            *mut i32,
        ) -> i32;
        let field = encode_form_field(context, field)?;
        let value = value
            .map(|value| encode_form_value(context, value))
            .transpose()?;
        let codex_agent_form_field_accepts: Accepts =
            symbol(context, b"codex_agent_form_field_accepts\0")?;
        let mut accepts = 0;
        check(
            unsafe {
                // SAFETY: inputs are live same-context handles and accepts is a valid output.
                codex_agent_form_field_accepts(
                    context.ptr(),
                    field.raw(),
                    value.as_ref().map_or(std::ptr::null_mut(), OwnedValue::raw),
                    &mut accepts,
                )
            },
            "test form-field acceptance",
        )?;
        match accepts {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a non-Boolean acceptance flag",
            )),
        }
    })
}

pub(crate) fn sync_elicitation_initial_values(
    elicitation: &Elicitation,
) -> Result<BTreeMap<String, FormValue>, CodexError> {
    with_sync_context(|context| {
        type InitialValues = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Elicitation,
            *mut *mut ffi::FormContent,
        ) -> i32;
        let elicitation = encode_elicitation(context, elicitation)?;
        let codex_agent_elicitation_initial_values: InitialValues =
            symbol(context, b"codex_agent_elicitation_initial_values\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: elicitation is live and raw is an initially-null typed output.
                codex_agent_elicitation_initial_values(context.ptr(), elicitation.raw(), &mut raw)
            },
            "read elicitation initial values",
        )?;
        decode_form_content(context, raw)
    })
}

pub(crate) fn sync_elicitation_validate(
    elicitation: &Elicitation,
    content: &BTreeMap<String, FormValue>,
) -> Result<ElicitationValidation, CodexError> {
    with_sync_context(|context| {
        type Validate = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Elicitation,
            *mut ffi::FormContent,
            *mut *mut ffi::ElicitationValidation,
        ) -> i32;
        let elicitation = encode_elicitation(context, elicitation)?;
        let content = encode_form_content(context, content)?;
        let codex_agent_elicitation_validate: Validate =
            symbol(context, b"codex_agent_elicitation_validate\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: both inputs are live same-context handles and raw starts null.
                codex_agent_elicitation_validate(
                    context.ptr(),
                    elicitation.raw(),
                    content.raw(),
                    &mut raw,
                )
            },
            "validate elicitation content",
        )?;
        decode_elicitation_validation(context, raw)
    })
}

pub(crate) fn sync_elicitation_accept(
    elicitation: &Elicitation,
    content: &BTreeMap<String, FormValue>,
) -> Result<ElicitationResponse, CodexError> {
    with_sync_context(|context| {
        type Accept = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Elicitation,
            *mut ffi::FormContent,
            *mut *mut ffi::ElicitationResponse,
        ) -> i32;
        let elicitation = encode_elicitation(context, elicitation)?;
        let native_content = encode_form_content(context, content)?;
        let codex_agent_elicitation_accept: Accept =
            symbol(context, b"codex_agent_elicitation_accept\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            unsafe {
                // SAFETY: both inputs are live same-context handles and raw starts null.
                codex_agent_elicitation_accept(
                    context.ptr(),
                    elicitation.raw(),
                    native_content.raw(),
                    &mut raw,
                )
            },
            "accept elicitation content",
        )?;
        decode_elicitation_response(context, raw, content.keys().cloned())
    })
}

pub(crate) fn sync_elicitation_accepts(
    elicitation: &Elicitation,
    response: &ElicitationResponse,
) -> Result<bool, CodexError> {
    with_sync_context(|context| {
        type Accepts = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Elicitation,
            *mut ffi::ElicitationResponse,
            *mut i32,
        ) -> i32;
        let elicitation = encode_elicitation(context, elicitation)?;
        let response = encode_elicitation_response(context, response)?;
        let codex_agent_elicitation_accepts: Accepts =
            symbol(context, b"codex_agent_elicitation_accepts\0")?;
        let mut accepts = 0;
        check(
            unsafe {
                // SAFETY: both inputs are live same-context handles and accepts is valid.
                codex_agent_elicitation_accepts(
                    context.ptr(),
                    elicitation.raw(),
                    response.raw(),
                    &mut accepts,
                )
            },
            "test elicitation response acceptance",
        )?;
        match accepts {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a non-Boolean acceptance flag",
            )),
        }
    })
}

fn encode_failure<'a>(
    context: &'a Arc<ContextInner>,
    failure: &CodexFailure,
) -> Result<OwnedValue<'a, ffi::Failure>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *const ffi::StringView,
        i32,
        *mut *mut ffi::Failure,
    ) -> i32;
    let create: Create = symbol(context, b"codex_agent_failure_create\0")?;
    let code = ffi::StringView::new(&failure.code);
    let message = ffi::StringView::new(&failure.message);
    create_owned(
        context,
        b"codex_agent_failure_release\0",
        "failure",
        |out| unsafe {
            // SAFETY: both views and the initially-null output remain live through this call.
            create(
                context.ptr(),
                &code,
                &message,
                flag(failure.recoverable),
                out,
            )
        },
    )
}

fn encode_pending_approval<'a>(
    context: &'a Arc<ContextInner>,
    approval: &PendingApproval,
) -> Result<OwnedValue<'a, ffi::PendingApproval>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const ffi::StringView,
        *mut ffi::ConversationId,
        *const ffi::StringView,
        *const ffi::StringView,
        *mut *mut ffi::PendingApproval,
    ) -> i32;
    let conversation_id = encode_conversation_id(context, &approval.conversation_id)?;
    let create: Create = symbol(context, b"codex_agent_pending_approval_create\0")?;
    let request_id = ffi::StringView::new(&approval.request_id);
    let title = ffi::StringView::new(&approval.title);
    let details = ffi::StringView::new(&approval.details);
    create_owned(
        context,
        b"codex_agent_pending_approval_destroy\0",
        "pending approval",
        |out| unsafe {
            // SAFETY: nested handle and views remain live through this copying call.
            create(
                context.ptr(),
                &request_id,
                conversation_id.raw(),
                &title,
                &details,
                out,
            )
        },
    )
}

fn encode_pending_elicitation<'a>(
    context: &'a Arc<ContextInner>,
    pending: &PendingElicitation,
) -> Result<OwnedValue<'a, ffi::PendingElicitation>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Elicitation,
        *mut *mut ffi::PendingElicitation,
    ) -> i32;
    let elicitation = encode_elicitation(context, &pending.elicitation)?;
    let create: Create = symbol(context, b"codex_agent_pending_elicitation_create\0")?;
    create_owned(
        context,
        b"codex_agent_pending_elicitation_destroy\0",
        "pending elicitation",
        |out| unsafe {
            // SAFETY: elicitation remains live through this copying call.
            create(context.ptr(), elicitation.raw(), out)
        },
    )
}

fn encode_pending_interaction<'a>(
    context: &'a Arc<ContextInner>,
    pending: &PendingInteraction,
) -> Result<OwnedValue<'a, ffi::PendingInteraction>, CodexError> {
    type FromApproval = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::PendingApproval,
        *mut *mut ffi::PendingInteraction,
    ) -> i32;
    type FromElicitation = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::PendingElicitation,
        *mut *mut ffi::PendingInteraction,
    ) -> i32;
    match pending {
        PendingInteraction::Approval(value) => {
            let value = encode_pending_approval(context, value)?;
            let wrap: FromApproval =
                symbol(context, b"codex_agent_pending_interaction_from_approval\0")?;
            create_owned(
                context,
                b"codex_agent_pending_interaction_destroy\0",
                "pending interaction",
                |out| unsafe {
                    // SAFETY: value remains live through this copying call.
                    wrap(context.ptr(), value.raw(), out)
                },
            )
        }
        PendingInteraction::Elicitation(value) => {
            let value = encode_pending_elicitation(context, value)?;
            let wrap: FromElicitation = symbol(
                context,
                b"codex_agent_pending_interaction_from_elicitation\0",
            )?;
            create_owned(
                context,
                b"codex_agent_pending_interaction_destroy\0",
                "pending interaction",
                |out| unsafe {
                    // SAFETY: value remains live through this copying call.
                    wrap(context.ptr(), value.raw(), out)
                },
            )
        }
    }
}

fn encode_interaction_state<'a>(
    context: &'a Arc<ContextInner>,
    state: &InteractionState,
) -> Result<OwnedValue<'a, ffi::InteractionState>, CodexError> {
    type Create = unsafe extern "C" fn(
        *mut ffi::Context,
        *const *mut ffi::PendingInteraction,
        usize,
        *const ffi::StringView,
        usize,
        i32,
        *mut ffi::Failure,
        *mut *mut ffi::InteractionState,
    ) -> i32;
    let pending = state
        .pending
        .iter()
        .map(|value| encode_pending_interaction(context, value))
        .collect::<Result<Vec<_>, _>>()?;
    let pending_raw = pending.iter().map(OwnedValue::raw).collect::<Vec<_>>();
    let resolving = state
        .resolving_request_ids
        .iter()
        .map(|value| ffi::StringView::new(value))
        .collect::<Vec<_>>();
    let failure = state
        .failure
        .as_ref()
        .map(|failure| encode_failure(context, failure))
        .transpose()?;
    let create: Create = symbol(context, b"codex_agent_interaction_state_create\0")?;
    create_owned(
        context,
        b"codex_agent_interaction_state_destroy\0",
        "interaction state",
        |out| unsafe {
            // SAFETY: all nested handles and views remain live through this copying call.
            create(
                context.ptr(),
                exact_array(&pending_raw),
                pending_raw.len(),
                exact_array(&resolving),
                resolving.len(),
                flag(failure.is_some()),
                failure
                    .as_ref()
                    .map_or(std::ptr::null_mut(), OwnedValue::raw),
                out,
            )
        },
    )
}

fn pending_identity(
    context: &Arc<ContextInner>,
    raw: *mut ffi::PendingInteraction,
) -> Result<(String, ConversationId), CodexError> {
    Ok((
        string(
            context,
            raw,
            b"codex_agent_pending_interaction_request_id_copy\0",
        )?,
        decode_conversation_id(
            context,
            child(
                context,
                raw,
                b"codex_agent_pending_interaction_conversation_id\0",
            )?,
        )?,
    ))
}

pub(crate) fn sync_interaction_state_is_resolving(
    state: &InteractionState,
    interaction: &PendingInteraction,
) -> Result<bool, CodexError> {
    with_sync_context(|context| {
        type PendingAt = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::InteractionState,
            usize,
            *mut *mut ffi::PendingInteraction,
        ) -> i32;
        type IsResolving = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::InteractionState,
            *mut ffi::PendingInteraction,
            *mut i32,
        ) -> i32;
        type ResolvingContains = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::InteractionState,
            *const ffi::StringView,
            *mut i32,
        ) -> i32;
        let state_handle = encode_interaction_state(context, state)?;
        let live_index = state
            .pending
            .iter()
            .position(|candidate| std::ptr::eq(candidate, interaction));
        let detached = live_index
            .is_none()
            .then(|| encode_pending_interaction(context, interaction))
            .transpose()?;
        let live = if let Some(index) = live_index {
            let pending_at: PendingAt =
                symbol(context, b"codex_agent_interaction_state_pending_at\0")?;
            Some(create_owned(
                context,
                b"codex_agent_pending_interaction_destroy\0",
                "pending interaction",
                |out| unsafe {
                    // SAFETY: index came from the exact immutable state input ordering.
                    pending_at(context.ptr(), state_handle.raw(), index, out)
                },
            )?)
        } else {
            None
        };
        let argument = live.as_ref().or(detached.as_ref()).ok_or_else(|| {
            CodexError::new(
                Status::InternalError,
                "missing pending-interaction argument",
            )
        })?;
        let codex_agent_interaction_state_is_resolving: IsResolving =
            symbol(context, b"codex_agent_interaction_state_is_resolving\0")?;
        let mut is_resolving = 0;
        check(
            unsafe {
                // SAFETY: both handles are live in the same context and output is valid.
                codex_agent_interaction_state_is_resolving(
                    context.ptr(),
                    state_handle.raw(),
                    argument.raw(),
                    &mut is_resolving,
                )
            },
            "test interaction resolution",
        )?;
        if !matches!(is_resolving, 0 | 1) {
            return Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a non-Boolean resolution flag",
            ));
        }
        if is_resolving == 1 || live_index.is_none() {
            return Ok(is_resolving == 1);
        }

        // A standalone C value constructor must deep-copy its pending list, so its child handles
        // cannot retain Rust reference identity. Recover only that language-level identity seam;
        // the canonical resolving-membership decision still comes from the verified C SDK.
        let contains: ResolvingContains = symbol(
            context,
            b"codex_agent_interaction_state_resolving_request_ids_contains\0",
        )?;
        let request_id = ffi::StringView::new(interaction.request_id());
        let mut resolving_contains = 0;
        check(
            unsafe {
                // SAFETY: state, borrowed request ID, and Boolean output follow the public ABI.
                contains(
                    context.ptr(),
                    state_handle.raw(),
                    &request_id,
                    &mut resolving_contains,
                )
            },
            "test resolving request-ID membership",
        )?;
        match resolving_contains {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(CodexError::new(
                Status::InternalError,
                "native C SDK returned a non-Boolean membership flag",
            )),
        }
    })
}

pub(crate) fn sync_interaction_state_pending_for(
    state: &InteractionState,
    conversation_id: &ConversationId,
) -> Result<Vec<usize>, CodexError> {
    with_sync_context(|context| {
        type PendingFor = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::InteractionState,
            *mut ffi::ConversationId,
            *mut *mut ffi::PendingInteractionList,
        ) -> i32;
        type PendingAt = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::PendingInteractionList,
            usize,
            *mut *mut ffi::PendingInteraction,
        ) -> i32;
        let state_handle = encode_interaction_state(context, state)?;
        let conversation_id_handle = encode_conversation_id(context, conversation_id)?;
        let codex_agent_interaction_state_pending_for: PendingFor =
            symbol(context, b"codex_agent_interaction_state_pending_for\0")?;
        let list = create_owned(
            context,
            b"codex_agent_pending_interaction_list_destroy\0",
            "pending-interaction list",
            |out| unsafe {
                // SAFETY: both inputs are live same-context handles and output starts null.
                codex_agent_interaction_state_pending_for(
                    context.ptr(),
                    state_handle.raw(),
                    conversation_id_handle.raw(),
                    out,
                )
            },
        )?;
        let length = count(
            context,
            list.raw(),
            b"codex_agent_pending_interaction_list_count\0",
        )?;
        let pending_at: PendingAt = symbol(context, b"codex_agent_pending_interaction_list_at\0")?;
        let mut used = vec![false; state.pending.len()];
        let mut indices = Vec::with_capacity(length);
        for list_index in 0..length {
            let pending = create_owned(
                context,
                b"codex_agent_pending_interaction_destroy\0",
                "pending interaction",
                |out| unsafe {
                    // SAFETY: list_index is within the measured immutable native list.
                    pending_at(context.ptr(), list.raw(), list_index, out)
                },
            )?;
            let identity = pending_identity(context, pending.raw())?;
            let index = state
                .pending
                .iter()
                .enumerate()
                .find(|(index, candidate)| {
                    !used[*index]
                        && candidate.request_id() == identity.0
                        && candidate.conversation_id() == &identity.1
                })
                .map(|(index, _)| index)
                .ok_or_else(|| {
                    CodexError::new(
                        Status::InternalError,
                        "native C SDK returned an unknown pending interaction",
                    )
                })?;
            used[index] = true;
            indices.push(index);
        }
        Ok(indices)
    })
}

#[cfg(all(test, target_os = "macos", target_arch = "aarch64"))]
mod real_sdk_tests {
    use super::*;
    use crate::CodexNativeLibrary;
    use libloading::Library;
    use std::path::{Path, PathBuf};
    use std::process::Command;

    type CreateMcpServer =
        unsafe extern "C" fn(*mut ffi::Context, i32, *mut i32, *mut *mut ffi::McpServer) -> i32;
    type CreateOrdinaryValue =
        unsafe extern "C" fn(*mut ffi::Context, i32, *mut *mut std::ffi::c_void) -> i32;

    fn compile_fixture(sdk: &Path) -> PathBuf {
        let output = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("target/real-value-graph/libcodex_agent_rust_value_fixture.dylib");
        std::fs::create_dir_all(output.parent().expect("fixture output parent"))
            .expect("create fixture output directory");
        let source =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/real_value_graph.c");
        let include = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../native/c-api/include");
        let result = Command::new("cc")
            .arg("-std=c11")
            .arg("-fPIC")
            .arg("-Wall")
            .arg("-Wextra")
            .arg("-Werror")
            .arg("-dynamiclib")
            .arg("-I")
            .arg(include)
            .arg(source)
            .arg(sdk)
            .arg(format!(
                "-Wl,-rpath,{}",
                sdk.parent().expect("SDK parent").display()
            ))
            .arg("-o")
            .arg(&output)
            .output()
            .expect("compile real value fixture");
        assert!(
            result.status.success(),
            "real value fixture compile failed:\n{}",
            String::from_utf8_lossy(&result.stderr)
        );
        output
    }

    fn create_server(
        fixture: &Library,
        context: &Arc<ContextInner>,
        variant: i32,
    ) -> *mut ffi::McpServer {
        // SAFETY: the fixture is compiled in this test from the exact declaration above.
        let create: libloading::Symbol<CreateMcpServer> = unsafe {
            fixture
                .get(b"codex_agent_test_mcp_server_fixture\0")
                .expect("load MCP fixture factory")
        };
        let mut stage = -1;
        let mut raw = std::ptr::null_mut();
        // SAFETY: the live context and initially-null typed output follow the fixture contract.
        let status = unsafe { create(context.ptr(), variant, &mut stage, &mut raw) };
        assert_eq!(
            status,
            ffi::STATUS_OK,
            "MCP fixture failed at stage {stage}"
        );
        assert_eq!(stage, 10);
        assert!(!raw.is_null());
        raw
    }

    fn create_ordinary(
        fixture: &Library,
        context: &Arc<ContextInner>,
        kind: i32,
    ) -> *mut std::ffi::c_void {
        // SAFETY: the fixture is compiled in this test from the exact declaration above.
        let create: libloading::Symbol<CreateOrdinaryValue> = unsafe {
            fixture
                .get(b"codex_agent_test_ordinary_value_fixture\0")
                .expect("load ordinary fixture factory")
        };
        let mut raw = std::ptr::null_mut();
        // SAFETY: the live context and initially-null output follow the fixture contract.
        let status = unsafe { create(context.ptr(), kind, &mut raw) };
        assert_eq!(
            status,
            ffi::STATUS_OK,
            "ordinary fixture kind {kind} failed"
        );
        assert!(!raw.is_null());
        raw
    }

    fn real_fixture() -> (CodexNativeLibrary, Arc<ContextInner>, Library) {
        let sdk = std::env::var_os("CODEX_AGENT_REAL_SDK")
            .map(PathBuf::from)
            .expect("set CODEX_AGENT_REAL_SDK");
        assert!(sdk.is_file(), "real C SDK is missing: {}", sdk.display());
        let fixture_path = compile_fixture(&sdk);
        let native = CodexNativeLibrary::load(&sdk).expect("load real C SDK");
        let context = ContextInner::create(native.inner.clone()).expect("create real context");
        // SAFETY: fixture_path names the just-compiled dylib and remains loaded for all calls.
        let fixture = unsafe { Library::new(fixture_path) }.expect("load real value fixture");
        (native, context, fixture)
    }

    #[test]
    #[ignore = "requires CODEX_AGENT_REAL_SDK pointing to the built macOS Arm64 C SDK"]
    fn real_ordinary_graph_decodes_every_owned_value_type() {
        let (_native, context, fixture) = real_fixture();

        let client = decode_client_info(
            &context,
            create_ordinary(&fixture, &context, 0).cast::<ffi::ClientInfoValue>(),
        )
        .expect("decode client info");
        assert_eq!(
            (&client.name, &client.title, &client.version),
            (&"one".into(), &"two".into(), &"three".into())
        );

        let failure = decode_failure_value(
            &context,
            create_ordinary(&fixture, &context, 1).cast::<ffi::Failure>(),
        )
        .expect("decode failure");
        assert_eq!(
            (
                failure.code.as_str(),
                failure.message.as_str(),
                failure.recoverable
            ),
            ("one", "two", true)
        );

        let workspace = decode_workspace(
            &context,
            create_ordinary(&fixture, &context, 2).cast::<ffi::Workspace>(),
        )
        .expect("decode workspace");
        assert_eq!(
            (workspace.path.as_str(), workspace.display_name.as_str()),
            ("one", "two")
        );

        let settings = decode_conversation_settings(
            &context,
            create_ordinary(&fixture, &context, 3).cast::<ffi::ConversationSettings>(),
        )
        .expect("decode conversation settings");
        assert_eq!(settings.approval_preset, ApprovalPreset::Strict);
        assert_eq!(settings.service_tier.as_deref(), Some("fast"));

        let summary = decode_conversation_summary(
            &context,
            create_ordinary(&fixture, &context, 4).cast::<ffi::ConversationSummary>(),
        )
        .expect("decode conversation summary");
        assert_eq!(summary.conversation_id.value, "one");
        assert_eq!(
            (summary.title.as_str(), summary.updated_at_epoch_seconds),
            ("two", 42)
        );

        let validation = decode_elicitation_validation(
            &context,
            create_ordinary(&fixture, &context, 5).cast::<ffi::ElicitationValidation>(),
        )
        .expect("decode validation");
        assert_eq!(validation.issues.len(), 2);
        assert!(!validation.is_valid());

        let option = decode_form_option(
            &context,
            create_ordinary(&fixture, &context, 6).cast::<ffi::FormOption>(),
        )
        .expect("decode form option");
        assert_eq!(
            (
                option.value.as_str(),
                option.title.as_str(),
                option.description.as_deref()
            ),
            ("one", "two", Some("three"))
        );

        let model = decode_model(
            &context,
            create_ordinary(&fixture, &context, 7).cast::<ffi::Model>(),
        )
        .expect("decode model");
        assert_eq!(model.supported_efforts, ["low", "high", "low"]);
        assert_eq!(model.service_tiers.len(), 2);
        assert_eq!(model.default_service_tier.as_deref(), Some("fast"));

        let catalog = decode_plugin_catalog(
            &context,
            create_ordinary(&fixture, &context, 8).cast::<ffi::PluginCatalog>(),
        )
        .expect("decode plugin catalog");
        assert_eq!(catalog.plugins.len(), 2);
        assert_eq!(
            catalog.plugins[0].reference.uri(),
            "plugin://tools@official"
        );

        let detail = decode_plugin_detail(
            &context,
            create_ordinary(&fixture, &context, 9).cast::<ffi::PluginDetail>(),
        )
        .expect("decode plugin detail");
        assert_eq!(
            (
                detail.skills.len(),
                detail.connectors.len(),
                detail.mcp_servers.len()
            ),
            (2, 2, 2)
        );
        assert_eq!(detail.hook_count, 17);

        let install = decode_plugin_install_result(
            &context,
            create_ordinary(&fixture, &context, 10).cast::<ffi::PluginInstallResult>(),
        )
        .expect("decode plugin install result");
        assert_eq!(install.connectors_needing_authentication.len(), 2);
        assert_eq!(install.message.as_deref(), Some("Authentication required"));

        let skills = decode_skill_catalog(
            &context,
            create_ordinary(&fixture, &context, 11).cast::<ffi::SkillCatalog>(),
        )
        .expect("decode skill catalog");
        assert_eq!(skills.skills.len(), 2);
        assert_eq!(skills.skills[0].dependencies, ["git", "git", "docker"]);

        let chunk = decode_skill_chunk(
            &context,
            create_ordinary(&fixture, &context, 12).cast::<ffi::SkillChunk>(),
        )
        .expect("decode skill chunk");
        assert_eq!(
            (chunk.content.as_str(), chunk.next_offset, chunk.total_bytes),
            ("one", Some(9), 12)
        );

        let turn = decode_turn_progress(
            &context,
            create_ordinary(&fixture, &context, 13).cast::<ffi::TurnProgress>(),
        )
        .expect("decode turn progress");
        assert_eq!(turn.plan_progress.expect("plan progress").steps.len(), 2);
        assert_eq!(turn.hook_activities.len(), 2);
        assert_eq!((turn.shell_exit_code, turn.is_truncated), (Some(-7), true));
    }

    #[test]
    #[ignore = "requires CODEX_AGENT_REAL_SDK pointing to the built macOS Arm64 C SDK"]
    fn real_mcp_graph_decodes_owned_values_and_destroys_every_root() {
        let (_native, context, fixture) = real_fixture();
        let stale_getter: ScalarI32<ffi::McpServer> =
            symbol(&context, b"codex_agent_mcp_server_can_remove\0").expect("load stale getter");

        for variant in 0..=2 {
            let raw = create_server(&fixture, &context, variant);
            let stale = raw;
            let server = decode_mcp_server(&context, raw).expect("decode real MCP server graph");
            assert_eq!(server.name, "server_1");
            assert_eq!(server.display_name, "Server One");
            match (
                variant,
                &server
                    .configuration
                    .as_ref()
                    .expect("configuration")
                    .transport,
            ) {
                (0, McpTransport::Http(http)) => {
                    assert_eq!(http.headers.as_ref().expect("headers").len(), 2);
                    assert_eq!(server.auth_status, McpAuthStatus::Oauth);
                    assert!(server.is_authorized());
                }
                (1, McpTransport::Stdio(stdio)) => {
                    assert_eq!(stdio.arguments, ["server.js", "--flag", "--flag"]);
                    assert_eq!(stdio.forwarded_environment.len(), 1);
                    assert!(!server.is_authorized());
                }
                (2, McpTransport::Http(http)) => {
                    assert_eq!(http.headers, None);
                    assert!(!server.is_authorized());
                }
                _ => panic!("fixture returned the wrong transport variant"),
            }
            let mut untouched = -1;
            assert_eq!(
                unsafe {
                    // SAFETY: stale input intentionally proves decoder ownership cleanup.
                    stale_getter(context.ptr(), stale, &mut untouched)
                },
                3
            );
            assert_eq!(untouched, -1);
        }

        let raw = create_server(&fixture, &context, 0);
        let stale = raw;
        let panic = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _owned = OwnedValue::new(
                &context,
                raw,
                b"codex_agent_mcp_server_destroy\0",
                "MCP panic test server",
            )
            .expect("own panic test server");
            panic!("intentional decoder panic");
        }));
        assert!(panic.is_err());
        let mut untouched = -1;
        assert_eq!(
            unsafe {
                // SAFETY: Drop must have destroyed this token during panic unwinding.
                stale_getter(context.ptr(), stale, &mut untouched)
            },
            3
        );
        assert_eq!(untouched, -1);
    }
}
