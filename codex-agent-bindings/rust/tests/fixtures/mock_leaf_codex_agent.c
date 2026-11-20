#include "mock_codex_agent.c"

typedef struct leaf { context_t *context; int32_t kind; int32_t owned_by_agent; } leaf_t;
typedef struct value {
    int32_t kind;
    int32_t index;
    int32_t generation;
    int32_t flag_a;
    int32_t flag_b;
    int64_t number;
    char text[96];
    char text2[96];
    char text3[96];
    char text4[96];
    char text5[96];
} value_t;
enum value_kind {
    VALUE_GENERIC,
    VALUE_API_KEY,
    VALUE_BROWSER_AUTH,
    VALUE_DEVICE_AUTH,
    VALUE_CONNECTOR,
    VALUE_HOOK,
    VALUE_INTEGRATION,
    VALUE_MCP_SERVER,
    VALUE_MCP_CONFIGURATION,
    VALUE_MCP_TRANSPORT,
    VALUE_MODEL,
    VALUE_PLUGIN,
    VALUE_SKILL,
    VALUE_PENDING_APPROVAL,
    VALUE_PENDING_ELICITATION,
    VALUE_INTERACTION_STATE,
    VALUE_AUTHENTICATION_STATE,
    VALUE_AUTHORIZATION_STATE,
    VALUE_ELICITATION_RESPONSE,
    VALUE_FORM_TEXT,
    VALUE_SERVICE_TIER,
    VALUE_CONVERSATION_ID,
    VALUE_CONVERSATION_SUMMARY,
    VALUE_CONVERSATION_VALUE,
    VALUE_MESSAGE,
    VALUE_INVOCATION,
    VALUE_INVOCATION_PLUGIN,
    VALUE_INVOCATION_SKILL,
    VALUE_TURN_REQUEST,
    VALUE_TURN_PROGRESS,
    VALUE_WORKSPACE
};
static _Atomic int32_t leaf_completion_mode = 1;
static _Atomic int32_t leaf_terminal = 1;
static _Atomic int32_t leaf_result = 0;
static _Atomic int32_t leaf_service_tier_present = 1;
static _Atomic int32_t leaf_release_count[9];
static _Atomic int32_t workspace_destroy_count = 0;

API void codex_agent_test_leaf_set_completion_mode(int32_t value) {
    atomic_store_explicit(&leaf_completion_mode, value, memory_order_release);
}

API void codex_agent_test_leaf_set_terminal(int32_t value) {
    atomic_store_explicit(&leaf_terminal, value, memory_order_release);
}

API void codex_agent_test_leaf_set_result(int32_t value) {
    atomic_store_explicit(&leaf_result, value, memory_order_release);
}

API void codex_agent_test_leaf_set_service_tier_present(int32_t value) {
    atomic_store_explicit(&leaf_service_tier_present, value, memory_order_release);
}

API void codex_agent_test_conversation_mode(int32_t value) {
    atomic_store_explicit(&conversation_test_mode, value, memory_order_release);
}

API void codex_agent_test_conversation_terminal(int32_t value) {
    atomic_store_explicit(&conversation_test_terminal, value, memory_order_release);
}

API status_t codex_agent_test_conversation_publish_after_cancel(context_t *context) {
    subscription_t *subscription = atomic_load_explicit(&conversation_subscription, memory_order_acquire);
    if (context == NULL || subscription == NULL) return 13;
    subscription->callback(context, subscription, 0,
        new_snapshot(SNAPSHOT_CONVERSATION, 77, subscription->owner), 0, subscription->user_data);
    return 0;
}

API int32_t codex_agent_test_leaf_release_count(int32_t kind) {
    if (kind < 0 || kind >= 9) return -1;
    return atomic_load_explicit(&leaf_release_count[kind], memory_order_acquire);
}

API int32_t codex_agent_test_workspace_destroy_count(void) {
    return atomic_load_explicit(&workspace_destroy_count, memory_order_acquire);
}

static status_t new_value(void **out) {
    if (out == NULL || *out != NULL) return 1;
    *out = calloc(1, sizeof(value_t));
    return *out == NULL ? 2 : 0;
}

static status_t new_typed_value(int32_t kind, int32_t index, int32_t generation, void **out) {
    status_t status = new_value(out);
    if (status != 0) return status;
    value_t *value = *out;
    value->kind = kind;
    value->index = index;
    value->generation = generation;
    return 0;
}

API status_t codex_agent_agent_workspace(context_t *context, agent_t *agent, value_t **out_workspace) {
    if (agent == NULL || agent->context != context) return 1;
    status_t status = new_typed_value(VALUE_WORKSPACE, 0, 0, (void **)out_workspace);
    if (status == 0) {
        (*out_workspace)->flag_a = 1;
        atomic_fetch_add_explicit(&agent_children_live, 1, memory_order_acq_rel);
    }
    return status;
}

API status_t codex_agent_workspace_destroy(context_t *context, value_t **workspace) {
    if (context == NULL || workspace == NULL || *workspace == NULL || (*workspace)->kind != VALUE_WORKSPACE) return 1;
    int32_t owned_by_agent = (*workspace)->flag_a;
    memset(*workspace, 0xA5, sizeof(**workspace));
    free(*workspace);
    *workspace = NULL;
    if (owned_by_agent) atomic_fetch_sub_explicit(&agent_children_live, 1, memory_order_acq_rel);
    atomic_fetch_add_explicit(&workspace_destroy_count, 1, memory_order_acq_rel);
    return 0;
}

API status_t codex_agent_workspace_path_copy(context_t *context, value_t *workspace, uint8_t *buffer, size_t capacity, size_t *required) {
    if (context == NULL || workspace == NULL || workspace->kind != VALUE_WORKSPACE) return 1;
    return copy_text("/agent-workspace", buffer, capacity, required);
}

API status_t codex_agent_workspace_display_name_copy(context_t *context, value_t *workspace, uint8_t *buffer, size_t capacity, size_t *required) {
    if (context == NULL || workspace == NULL || workspace->kind != VALUE_WORKSPACE) return 1;
    return copy_text("Agent Workspace", buffer, capacity, required);
}

static int view_equals(const string_view_t *value, const char *expected) {
    size_t size = strlen(expected);
    return value != NULL && value->size == size &&
        (size == 0 || (value->data != NULL && memcmp(value->data, expected, size) == 0));
}

static void copy_view(char *out, size_t capacity, const string_view_t *value) {
    size_t size = value == NULL ? 0 : value->size;
    if (size >= capacity) size = capacity - 1;
    if (size != 0 && value->data != NULL) memcpy(out, value->data, size);
    out[size] = '\0';
}

static int typed_text(void *raw, int32_t kind, const char *text) {
    value_t *value = raw;
    return value != NULL && value->kind == kind && strcmp(value->text, text) == 0;
}

static status_t destroy_value(void **value) {
    if (value == NULL || *value == NULL) return 0;
    free(*value);
    *value = NULL;
    return 0;
}

API status_t codex_agent_test_leaf_service(context_t *context, int32_t kind, void **out_service) {
    if (context == NULL || kind < 0 || kind >= 9 || out_service == NULL || *out_service != NULL) return 1;
    leaf_t *leaf = calloc(1, sizeof(leaf_t));
    leaf->context = context;
    leaf->kind = kind;
    *out_service = leaf;
    return 0;
}

#define AGENT_LEAF_GETTER(name, expected_kind) \
API status_t name(context_t *context, agent_t *agent, leaf_t **out_service) { \
    if (agent == NULL || agent->context != context || out_service == NULL || *out_service != NULL) return 1; \
    leaf_t *leaf = calloc(1, sizeof(*leaf)); \
    if (leaf == NULL) return 2; \
    leaf->context = context; leaf->kind = expected_kind; leaf->owned_by_agent = 1; \
    *out_service = leaf; \
    atomic_fetch_add_explicit(&agent_children_live, 1, memory_order_acq_rel); \
    return 0; \
}
AGENT_LEAF_GETTER(codex_agent_agent_authentication, 0)
AGENT_LEAF_GETTER(codex_agent_agent_connectors, 1)
AGENT_LEAF_GETTER(codex_agent_agent_hooks, 2)
AGENT_LEAF_GETTER(codex_agent_agent_integration_authorization, 3)
AGENT_LEAF_GETTER(codex_agent_agent_interactions, 4)
AGENT_LEAF_GETTER(codex_agent_agent_mcp_servers, 5)
AGENT_LEAF_GETTER(codex_agent_agent_models, 6)
AGENT_LEAF_GETTER(codex_agent_agent_plugins, 7)
AGENT_LEAF_GETTER(codex_agent_agent_skills, 8)
#undef AGENT_LEAF_GETTER

#define LEAF_RELEASE(name, expected_kind) \
API status_t name(context_t *context, leaf_t **value) { \
    if (value == NULL || *value == NULL) return 0; \
    if ((*value)->context != context || (*value)->kind != (expected_kind)) return 5; \
    int32_t owned_by_agent = (*value)->owned_by_agent; \
    free(*value); *value = NULL; \
    if (owned_by_agent) atomic_fetch_sub_explicit(&agent_children_live, 1, memory_order_acq_rel); \
    atomic_fetch_add_explicit(&leaf_release_count[expected_kind], 1, memory_order_acq_rel); \
    return 0; \
}
LEAF_RELEASE(codex_agent_authentication_release, 0)
LEAF_RELEASE(codex_agent_connectors_release, 1)
LEAF_RELEASE(codex_agent_hooks_release, 2)
LEAF_RELEASE(codex_agent_integration_authorization_release, 3)
LEAF_RELEASE(codex_agent_interactions_release, 4)
LEAF_RELEASE(codex_agent_mcp_servers_release, 5)
LEAF_RELEASE(codex_agent_models_release, 6)
LEAF_RELEASE(codex_agent_plugins_release, 7)
LEAF_RELEASE(codex_agent_skills_release, 8)

static status_t leaf_operation(context_t *context, leaf_t *service, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (service == NULL || service->context != context) return 5;
    return start_operation(context, atomic_load_explicit(&leaf_result, memory_order_acquire), 0, atomic_load_explicit(&leaf_completion_mode, memory_order_acquire), callback, user_data, out_operation);
}

#define OP0(name) API status_t name(context_t *c, leaf_t *s, operation_callback_t cb, void *u, operation_t **o) { return leaf_operation(c,s,cb,u,o); }

API status_t codex_agent_authentication_authenticate_api_key(context_t *c, leaf_t *s, value_t *a, operation_callback_t cb, void *u, operation_t **o) {
    if (!typed_text(a, VALUE_API_KEY, "secret") || a->generation != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_authentication_authenticate_chat_gpt_browser(context_t *c, leaf_t *s, value_t *a, operation_callback_t cb, void *u, operation_t **o) {
    if (a == NULL || a->kind != VALUE_BROWSER_AUTH) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_authentication_authenticate_chat_gpt_device_code(context_t *c, leaf_t *s, value_t *a, operation_callback_t cb, void *u, operation_t **o) {
    if (a == NULL || a->kind != VALUE_DEVICE_AUTH) return 1;
    return leaf_operation(c,s,cb,u,o);
}
OP0(codex_agent_authentication_cancel)
OP0(codex_agent_authentication_sign_out)
API status_t codex_agent_integration_authorization_authorize(context_t *c, leaf_t *s, value_t *a, operation_callback_t cb, void *u, operation_t **o) {
    if (a == NULL || a->kind != VALUE_INTEGRATION ||
        a->generation != 1 || !((a->flag_a == 0 && strcmp(a->text, "connector") == 0) ||
          (a->flag_a == 1 && strcmp(a->text, "server") == 0))) return 1;
    return leaf_operation(c,s,cb,u,o);
}
OP0(codex_agent_integration_authorization_cancel)
OP0(codex_agent_models_list)
API status_t codex_agent_models_resolve(context_t *c, leaf_t *s, int32_t resolution, operation_callback_t cb, void *u, operation_t **o) {
    if (resolution != 2) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_models_resolve_effort(context_t *c, leaf_t *s, value_t *model, int32_t resolution, operation_callback_t cb, void *u, operation_t **o) {
    if (!typed_text(model, VALUE_MODEL, "model") || model->generation != 1 || resolution != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_models_resolve_service_tier(context_t *c, leaf_t *s, value_t *model, int32_t resolution, operation_callback_t cb, void *u, operation_t **o) {
    if (!typed_text(model, VALUE_MODEL, "model") || model->generation != 1 || resolution != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_skills_list(context_t *c, leaf_t *s, int32_t force_refresh, operation_callback_t cb, void *u, operation_t **o) {
    if (force_refresh != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_skills_read(context_t *c, leaf_t *s, const string_view_t *p, int64_t offset, operation_callback_t cb, void *u, operation_t **o) {
    if (!view_equals(p, "skill.md") || offset != 7) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_skills_install(context_t *c, leaf_t *s, const string_view_t *p, int32_t scope, operation_callback_t cb, void *u, operation_t **o) {
    if (!view_equals(p, "skills") || scope != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_skills_uninstall(context_t *c, leaf_t *s, value_t *skill, operation_callback_t cb, void *u, operation_t **o) {
    if (!typed_text(skill, VALUE_SKILL, "skill") || skill->generation != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
OP0(codex_agent_hooks_list)
API status_t codex_agent_hooks_install(context_t *c, leaf_t *s, const string_view_t *p, int32_t scope, operation_callback_t cb, void *u, operation_t **o) {
    if (!view_equals(p, "hooks") || scope != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}
static int expected_hook(value_t *hook) {
    return typed_text(hook, VALUE_HOOK, "hook") && hook->generation == 1;
}
API status_t codex_agent_hooks_uninstall(context_t *c, leaf_t *s, value_t *hook, operation_callback_t cb, void *u, operation_t **o) {
    if (!expected_hook(hook)) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_hooks_trust(context_t *c, leaf_t *s, value_t *hook, operation_callback_t cb, void *u, operation_t **o) {
    if (!expected_hook(hook)) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_plugins_list(context_t *c, leaf_t *s, int32_t force_refresh, operation_callback_t cb, void *u, operation_t **o) {
    if (force_refresh != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
static int expected_plugin(value_t *plugin) {
    return typed_text(plugin, VALUE_PLUGIN, "plugin-id") && plugin->generation == 1;
}
#define PLUGIN_OP(name) API status_t name(context_t *c, leaf_t *s, value_t *plugin, operation_callback_t cb, void *u, operation_t **o) { if (!expected_plugin(plugin)) return 1; return leaf_operation(c,s,cb,u,o); }
PLUGIN_OP(codex_agent_plugins_read)
PLUGIN_OP(codex_agent_plugins_install)
PLUGIN_OP(codex_agent_plugins_uninstall)
API status_t codex_agent_connectors_list(context_t *c, leaf_t *s, int32_t force_refresh, operation_callback_t cb, void *u, operation_t **o) {
    if (force_refresh != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
OP0(codex_agent_mcp_servers_list)
API status_t codex_agent_mcp_servers_add(context_t *c, leaf_t *s, value_t *configuration, operation_callback_t cb, void *u, operation_t **o) {
    if (!typed_text(configuration, VALUE_MCP_CONFIGURATION, "server") || configuration->generation != 1) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_mcp_servers_remove(context_t *c, leaf_t *s, value_t *server, operation_callback_t cb, void *u, operation_t **o) {
    if (!typed_text(server, VALUE_MCP_SERVER, "server") || server->generation != 1 || server->flag_b != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_interactions_open_url(context_t *c, leaf_t *s, value_t *pending, operation_callback_t cb, void *u, operation_t **o) {
    if (pending == NULL || pending->kind != VALUE_PENDING_ELICITATION || pending->index % 3 != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_interactions_resolve_approval(context_t *c, leaf_t *s, value_t *pending, int32_t decision, operation_callback_t cb, void *u, operation_t **o) {
    if (pending == NULL || pending->kind != VALUE_PENDING_APPROVAL || pending->index % 3 != 0 || decision != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}
API status_t codex_agent_interactions_resolve_elicitation(context_t *c, leaf_t *s, value_t *pending, value_t *response, operation_callback_t cb, void *u, operation_t **o) {
    if (pending == NULL || pending->kind != VALUE_PENDING_ELICITATION || pending->index % 3 != 0 || response == NULL ||
        response->kind != VALUE_ELICITATION_RESPONSE || response->generation != 1 ||
        strcmp(response->text, "answer") != 0 || strcmp(response->text2, "yes") != 0) return 1;
    return leaf_operation(c,s,cb,u,o);
}

#define AVAILABLE(name) API status_t name(context_t *c, leaf_t *s, int32_t *out) { if (s == NULL || s->context != c || out == NULL) return 1; *out = 1; return 0; }
AVAILABLE(codex_agent_skills_is_available)
AVAILABLE(codex_agent_hooks_is_available)
AVAILABLE(codex_agent_plugins_is_available)
AVAILABLE(codex_agent_connectors_is_available)
AVAILABLE(codex_agent_mcp_servers_is_available)

static status_t leaf_get(context_t *c, leaf_t *s, snapshot_t **out) {
    if (s == NULL || s->context != c || out == NULL || *out != NULL) return 1;
    *out = new_snapshot(SNAPSHOT_HOST, 0, s); return 0;
}
static status_t leaf_subscribe(context_t *c, leaf_t *s, state_callback_t cb, void *u, subscription_t **out) {
    if (s == NULL || s->context != c || cb == NULL || out == NULL || *out != NULL) return 1;
    subscription_t *sub = calloc(1, sizeof(subscription_t)); sub->context=c; sub->callback=cb; sub->user_data=u; atomic_init(&sub->destroy_attempts,0); *out=sub;
    cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, 0, s), 0, u);
    if (atomic_load_explicit(&leaf_terminal, memory_order_acquire)) {
        cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, 1, s), 0, u);
        cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, 2, s), 1, u);
    }
    return 0;
}
#define STATE_PAIR(prefix) \
API status_t prefix##_get(context_t *c, leaf_t *s, snapshot_t **o) { return leaf_get(c,s,o); } \
API status_t prefix##_subscribe(context_t *c, leaf_t *s, state_callback_t cb, void *u, subscription_t **o) { return leaf_subscribe(c,s,cb,u,o); }
STATE_PAIR(codex_agent_authentication_state)
STATE_PAIR(codex_agent_authentication_is_authenticated)
STATE_PAIR(codex_agent_authentication_is_authenticating)
STATE_PAIR(codex_agent_integration_authorization_state)
API status_t codex_agent_integration_authorization_active_get(context_t *c, leaf_t *s, snapshot_t **out) {
    if (s == NULL || s->context != c || out == NULL || *out != NULL) return 1;
    *out = new_snapshot(SNAPSHOT_HOST, -1, s);
    return 0;
}
API status_t codex_agent_integration_authorization_active_subscribe(context_t *c, leaf_t *s, state_callback_t cb, void *u, subscription_t **out) {
    if (s == NULL || s->context != c || cb == NULL || out == NULL || *out != NULL) return 1;
    subscription_t *sub = calloc(1, sizeof(subscription_t)); sub->context=c; sub->callback=cb; sub->user_data=u; atomic_init(&sub->destroy_attempts,0); *out=sub;
    cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, -1, s), 0, u);
    if (atomic_load_explicit(&leaf_terminal, memory_order_acquire)) {
        cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, 0, s), 0, u);
        cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, 1, s), 0, u);
        cb(c, sub, 0, new_snapshot(SNAPSHOT_HOST, 2, s), 1, u);
    }
    return 0;
}
STATE_PAIR(codex_agent_integration_authorization_is_authorizing)
STATE_PAIR(codex_agent_interactions_state)
STATE_PAIR(codex_agent_interactions_approvals)
STATE_PAIR(codex_agent_interactions_elicitations)

API status_t codex_agent_state_boolean_value(context_t *c, snapshot_t *s, int32_t *out) { (void)c; if (s == NULL || out == NULL) return 1; *out=(s->value % 2)==0; return 0; }
API status_t codex_agent_authentication_state_value(context_t *c, snapshot_t *s, void **out) { (void)c; if (s == NULL) return 1; return new_typed_value(VALUE_AUTHENTICATION_STATE, 0, s->value, out); }
API status_t codex_agent_integration_authorization_state_value(context_t *c, snapshot_t *s, void **out) { (void)c; if (s == NULL) return 1; return new_typed_value(VALUE_AUTHORIZATION_STATE, 0, s->value, out); }
API status_t codex_agent_integration_authorization_active_has_value(context_t *c, snapshot_t *s, int32_t *out) { (void)c; if (s == NULL || out == NULL) return 1; *out=s->value >= 0 && s->value < 2; return 0; }
API status_t codex_agent_integration_authorization_active_value(context_t *c, snapshot_t *s, void **out) { (void)c; if (s == NULL || s->value < 0 || s->value >= 2) return 1; return new_typed_value(VALUE_INTEGRATION, 0, s->value, out); }
API status_t codex_agent_interactions_state_value(context_t *c, snapshot_t *s, void **out) { (void)c; if (s == NULL) return 1; return new_typed_value(VALUE_INTERACTION_STATE, 0, s->value, out); }

#define DESTROY(name) API status_t name(context_t *c, void **v) { (void)c; return destroy_value(v); }
#define COPY(name, text) API status_t name(context_t *c, void *v, uint8_t *b, size_t n, size_t *r) { (void)c; if (v == NULL) return 1; return copy_text(text,b,n,r); }
#define I32(name, value) API status_t name(context_t *c, void *v, int32_t *out) { (void)c; if (v == NULL || out == NULL) return 1; *out=(value); return 0; }
#define I64(name, value) API status_t name(context_t *c, void *v, int64_t *out) { (void)c; if (v == NULL || out == NULL) return 1; *out=(value); return 0; }
#define COUNT(name, value) API status_t name(context_t *c, void *v, size_t *out) { (void)c; if (v == NULL || out == NULL) return 1; *out=(value); return 0; }
#define CHILD(name) API status_t name(context_t *c, void *v, void **out) { (void)c; if (v == NULL) return 1; return new_value(out); }
#define COPY_AT(name) API status_t name(context_t*c,void*v,size_t i,uint8_t*b,size_t n,size_t*r){(void)c;(void)v;(void)i;(void)b;(void)n;(void)r;return 13;}
#define CHILD_AT(name) API status_t name(context_t*c,void*v,size_t i,void**out){(void)c;(void)v;(void)i;(void)out;return 13;}

DESTROY(codex_agent_authentication_state_destroy)
API status_t codex_agent_authentication_state_status(context_t *c, value_t *v, int32_t *out) { (void)c; if (v == NULL || v->kind != VALUE_AUTHENTICATION_STATE || out == NULL) return 1; *out=v->generation; return 0; }
I32(codex_agent_authentication_state_has_pending_sign_in_url, 0)
I32(codex_agent_authentication_state_has_device_verification_url, 0)
I32(codex_agent_authentication_state_has_device_user_code, 0)
I32(codex_agent_authentication_state_has_failure, 0)

DESTROY(codex_agent_integration_authorization_state_destroy)
API status_t codex_agent_integration_authorization_state_status(context_t *c, value_t *v, int32_t *out) { (void)c; if (v == NULL || v->kind != VALUE_AUTHORIZATION_STATE || out == NULL) return 1; *out=v->generation; return 0; }
API status_t codex_agent_integration_authorization_state_target(context_t *c, void *v, void **out) { (void)c;(void)v;(void)out;return 13; }
API status_t codex_agent_integration_authorization_state_failure(context_t *c, void *v, void **out) { (void)c;(void)v;(void)out;return 13; }

static size_t state_collection_count(int32_t generation) { return generation == 0 ? 3 : generation == 1 ? 1 : 2; }
API status_t codex_agent_interactions_approvals_count(context_t *c, snapshot_t *s, size_t *out) { (void)c; if (s==NULL || out==NULL) return 1; *out=state_collection_count(s->value); return 0; }
API status_t codex_agent_interactions_elicitations_count(context_t *c, snapshot_t *s, size_t *out) { (void)c; if (s==NULL || out==NULL) return 1; *out=state_collection_count(s->value); return 0; }
API status_t codex_agent_interactions_approvals_at(context_t *c, snapshot_t *s, size_t i, void **out) { (void)c; if (s==NULL || i>=state_collection_count(s->value)) return 1; return new_typed_value(VALUE_PENDING_APPROVAL, (int32_t)i, s->value, out); }
API status_t codex_agent_interactions_elicitations_at(context_t *c, snapshot_t *s, size_t i, void **out) { (void)c; if (s==NULL || i>=state_collection_count(s->value)) return 1; return new_typed_value(VALUE_PENDING_ELICITATION, (int32_t)i, s->value, out); }
DESTROY(codex_agent_pending_approval_destroy)
API status_t codex_agent_pending_approval_request_id_copy(context_t *c, value_t *v, uint8_t *b, size_t n, size_t *r) { (void)c; if (v==NULL || v->kind!=VALUE_PENDING_APPROVAL) return 1; const char *ids[]={"approval-a","approval-b","approval-a"}; return copy_text(ids[v->index % 3],b,n,r); }
COPY(codex_agent_pending_approval_title_copy, "Approve")
COPY(codex_agent_pending_approval_details_copy, "details")
API status_t codex_agent_pending_approval_conversation_id(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_PENDING_APPROVAL)return 1;return new_typed_value(VALUE_GENERIC,v->index,v->generation,out);}
DESTROY(codex_agent_pending_elicitation_destroy)
API status_t codex_agent_pending_elicitation_elicitation(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_PENDING_ELICITATION)return 1;return new_typed_value(VALUE_PENDING_ELICITATION,v->index,v->generation,out);}
DESTROY(codex_agent_elicitation_destroy)
API status_t codex_agent_elicitation_request_id_copy(context_t *c, value_t *v, uint8_t *b, size_t n, size_t *r) { (void)c; if (v==NULL || v->kind!=VALUE_PENDING_ELICITATION) return 1; const char *ids[]={"elicitation-a","elicitation-b","elicitation-a"}; return copy_text(ids[v->index % 3],b,n,r); }
COPY(codex_agent_elicitation_server_name_copy, "server")
COPY(codex_agent_elicitation_message_copy, "message")
CHILD(codex_agent_elicitation_conversation_id)
I32(codex_agent_elicitation_has_form, 0)
I32(codex_agent_elicitation_has_url, 0)
DESTROY(codex_agent_conversation_id_destroy)
API status_t codex_agent_conversation_id_create(context_t*c,const string_view_t*input,void**out){(void)c;status_t status=new_typed_value(VALUE_CONVERSATION_ID,0,0,out);if(status==0)copy_view(((value_t*)*out)->text,sizeof(((value_t*)*out)->text),input);return status;}
API status_t codex_agent_conversation_id_value_copy(context_t*c,value_t*v,uint8_t*b,size_t n,size_t*r){(void)c;if(v==NULL)return 1;return copy_text(v->kind==VALUE_CONVERSATION_ID?v->text:"conversation-1",b,n,r);}

DESTROY(codex_agent_interaction_state_destroy)
API status_t codex_agent_interaction_state_pending_count(context_t*c,value_t*v,size_t*out){(void)c;if(v==NULL||v->kind!=VALUE_INTERACTION_STATE||out==NULL)return 1;*out=v->generation==1?0:1;return 0;}
API status_t codex_agent_interaction_state_pending_at(context_t*c,value_t*v,size_t i,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INTERACTION_STATE||v->generation==1||i!=0)return 1;return new_typed_value(VALUE_PENDING_APPROVAL,0,v->generation,out);}
DESTROY(codex_agent_pending_interaction_destroy)
I32(codex_agent_pending_interaction_kind, 0)
API status_t codex_agent_pending_interaction_approval(context_t*c,value_t*v,void**out){(void)c;if(v==NULL)return 1;return new_typed_value(VALUE_PENDING_APPROVAL,v->index,v->generation,out);}
COUNT(codex_agent_interaction_state_resolving_request_ids_count, 0)
API status_t codex_agent_interaction_state_resolving_request_ids_contains(context_t*c,void*v,const void*id,int32_t*out){(void)c;(void)v;(void)id;if(out==NULL)return 1;*out=0;return 0;}
I32(codex_agent_interaction_state_has_failure, 0)
API status_t codex_agent_interaction_state_failure(context_t*c,void*v,void**out){(void)c;(void)v;(void)out;return 13;}

#define CREATE0(name) API status_t name(context_t *c, void **out) { (void)c; return new_value(out); }
#define CREATE1(name) API status_t name(context_t *c, const void *a, void **out) { (void)c; if (a==NULL) return 1; return new_value(out); }
#define SIMPLE_DESTROY(name) DESTROY(name)
API status_t codex_agent_authentication_method_api_key_create(context_t *c, const string_view_t *key, void **out) { (void)c; status_t status=new_typed_value(VALUE_API_KEY,0,view_equals(key,"secret"),out); if(status==0)copy_view(((value_t*)*out)->text,sizeof(((value_t*)*out)->text),key); return status; }
API status_t codex_agent_authentication_method_chat_gpt_browser_create(context_t *c, void **out) { (void)c; return new_typed_value(VALUE_BROWSER_AUTH,0,0,out); }
API status_t codex_agent_authentication_method_chat_gpt_device_code_create(context_t *c, void **out) { (void)c; return new_typed_value(VALUE_DEVICE_AUTH,0,0,out); }
SIMPLE_DESTROY(codex_agent_authentication_method_api_key_destroy)
SIMPLE_DESTROY(codex_agent_authentication_method_chat_gpt_browser_destroy)
SIMPLE_DESTROY(codex_agent_authentication_method_chat_gpt_device_code_destroy)

API status_t codex_agent_model_create(context_t *c, const string_view_t *id, const string_view_t *display, const string_view_t *description, const string_view_t *efforts, size_t effort_count, const string_view_t *default_effort, int32_t is_default, void *const *tiers, size_t tier_count, int32_t has_default_tier, const string_view_t *default_tier, void **out) {
    (void)c;(void)display;(void)description;(void)tiers;(void)default_tier;
    status_t status=new_typed_value(VALUE_MODEL,0,0,out); if(status!=0)return status;
    value_t *value=*out; copy_view(value->text,sizeof(value->text),id); copy_view(value->text2,sizeof(value->text2),default_effort);
    if(effort_count!=0)copy_view(value->text3,sizeof(value->text3),&efforts[0]);
    value->flag_a=is_default; value->flag_b=has_default_tier; value->number=(int64_t)(effort_count * 100 + tier_count);
    value->generation=view_equals(id,"model")&&view_equals(display,"Model")&&view_equals(description,"")&&effort_count==1&&view_equals(&efforts[0],"medium")&&view_equals(default_effort,"medium")&&is_default==1&&tier_count==0&&has_default_tier==0; return 0;
}
DESTROY(codex_agent_model_destroy)
API status_t codex_agent_service_tier_create(context_t *c,const void*a,const void*b,const void*d,void**out){(void)c;(void)a;(void)b;(void)d;return new_value(out);}
DESTROY(codex_agent_service_tier_destroy)
API status_t codex_agent_plugin_reference_create(context_t*c,const string_view_t*id,const string_view_t*name,const string_view_t*market,int32_t has_path,const string_view_t*path,int32_t has_remote,const string_view_t*remote,void**out){(void)c;(void)path;(void)remote;status_t status=new_typed_value(VALUE_PLUGIN,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),id);copy_view(v->text2,sizeof(v->text2),name);copy_view(v->text3,sizeof(v->text3),market);v->flag_a=has_path;v->flag_b=has_remote;v->generation=view_equals(id,"plugin-id")&&view_equals(name,"plugin")&&view_equals(market,"market")&&has_path==0&&has_remote==0;return 0;}
DESTROY(codex_agent_plugin_reference_destroy)
API status_t codex_agent_skill_create(context_t*c,const string_view_t*name,const string_view_t*display,const string_view_t*description,const string_view_t*path,int32_t scope,int32_t enabled,int32_t has_brand,const string_view_t*brand,const string_view_t*dependencies,size_t dependency_count,int32_t can_uninstall,int32_t has_origin,int32_t origin,void**out){(void)c;(void)brand;(void)dependencies;status_t status=new_typed_value(VALUE_SKILL,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),name);copy_view(v->text2,sizeof(v->text2),path);v->flag_a=scope;v->flag_b=enabled;v->number=(int64_t)(dependency_count*1000+can_uninstall*100+has_origin*10+origin);v->generation=view_equals(name,"skill")&&view_equals(display,"Skill")&&view_equals(description,"skill")&&view_equals(path,"skill.md")&&scope==0&&enabled==1&&has_brand==0&&dependency_count==0&&can_uninstall==1&&has_origin==1&&origin==0;return 0;}
DESTROY(codex_agent_skill_destroy)

CREATE0(codex_agent_hook_handler_agent_acquire)
CREATE0(codex_agent_hook_handler_prompt_acquire)
DESTROY(codex_agent_hook_handler_agent_destroy)
DESTROY(codex_agent_hook_handler_prompt_destroy)
API status_t codex_agent_hook_handler_command_create(context_t*c,const void*a,int32_t b,void**out){(void)c;(void)a;(void)b;return new_value(out);}
API status_t codex_agent_hook_handler_mcp_tool_create(context_t*c,const void*a,const void*b,void**out){(void)c;(void)a;(void)b;return new_value(out);}
DESTROY(codex_agent_hook_handler_command_destroy)
DESTROY(codex_agent_hook_handler_mcp_tool_destroy)
CREATE1(codex_agent_hook_handler_from_agent)
CREATE1(codex_agent_hook_handler_from_prompt)
CREATE1(codex_agent_hook_handler_from_command)
CREATE1(codex_agent_hook_handler_from_mcp_tool)
DESTROY(codex_agent_hook_handler_destroy)
API status_t codex_agent_hook_create(context_t*c,const string_view_t*key,const string_view_t*hash,int32_t enabled,const string_view_t*event,void*handler,int32_t managed,const string_view_t*source,const string_view_t*path,int64_t timeout,int32_t trust,int32_t has_matcher,const string_view_t*matcher,int32_t has_plugin,const string_view_t*plugin,int32_t has_status,const string_view_t*status_text,int32_t has_origin,int32_t origin,int32_t can_uninstall,void**out){(void)c;(void)matcher;(void)plugin;(void)status_text;status_t status=new_typed_value(VALUE_HOOK,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),key);copy_view(v->text2,sizeof(v->text2),path);copy_view(v->text3,sizeof(v->text3),hash);copy_view(v->text4,sizeof(v->text4),event);copy_view(v->text5,sizeof(v->text5),source);v->flag_a=enabled;v->number=timeout;v->generation=view_equals(key,"hook")&&view_equals(hash,"hash")&&enabled==1&&view_equals(event,"afterTurn")&&handler!=NULL&&managed==0&&view_equals(source,"USER")&&view_equals(path,"hooks")&&timeout==10&&trust==2&&has_matcher==0&&has_plugin==0&&has_status==0&&has_origin==1&&origin==0&&can_uninstall==1;return 0;}
DESTROY(codex_agent_hook_destroy)

API status_t codex_agent_mcp_environment_variable_create(context_t*c,const void*a,int32_t b,int32_t d,void**out){(void)c;(void)a;(void)b;(void)d;return new_value(out);}
DESTROY(codex_agent_mcp_environment_variable_destroy)
API status_t codex_agent_mcp_oauth_configuration_create(context_t*c,int32_t a,const void*b,int32_t d,int32_t e,void**out){(void)c;(void)a;(void)b;(void)d;(void)e;return new_value(out);}
DESTROY(codex_agent_mcp_oauth_configuration_destroy)
API status_t codex_agent_mcp_tool_configuration_create(context_t*c,int32_t a,int32_t b,void**out){(void)c;(void)a;(void)b;return new_value(out);}
DESTROY(codex_agent_mcp_tool_configuration_destroy)
API status_t codex_agent_mcp_transport_http_create(context_t*c,const void*a,int32_t b,const void*d,int32_t e,const void*f,const void*g,size_t h,int32_t i,const void*j,const void*k,size_t l,int32_t m,const void*n,void**out){(void)c;(void)a;(void)b;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;(void)j;(void)k;(void)l;(void)m;(void)n;return new_value(out);}
API status_t codex_agent_mcp_transport_stdio_create(context_t*c,const string_view_t*command,const string_view_t*arguments,size_t argument_count,int32_t has_working_directory,const string_view_t*working_directory,int32_t has_environment,const string_view_t*environment_keys,const string_view_t*environment_values,size_t environment_count,void*const*forwarded,size_t forwarded_count,void**out){(void)c;(void)arguments;(void)working_directory;(void)environment_keys;(void)environment_values;(void)forwarded;status_t status=new_typed_value(VALUE_MCP_TRANSPORT,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),command);v->flag_a=has_working_directory;v->flag_b=has_environment;v->number=(int64_t)(argument_count*10000+environment_count*100+forwarded_count);v->generation=view_equals(command,"tool")&&argument_count==0&&has_working_directory==0&&has_environment==0&&environment_count==0&&forwarded_count==0;return 0;}
DESTROY(codex_agent_mcp_transport_http_destroy)
DESTROY(codex_agent_mcp_transport_stdio_destroy)
CREATE1(codex_agent_mcp_transport_from_http)
API status_t codex_agent_mcp_transport_from_stdio(context_t*c,value_t*input,void**out){(void)c;if(input==NULL||input->kind!=VALUE_MCP_TRANSPORT)return 1;status_t status=new_typed_value(VALUE_MCP_TRANSPORT,0,0,out);if(status==0)**(value_t**)out=*input;return status;}
DESTROY(codex_agent_mcp_transport_destroy)
API status_t codex_agent_mcp_server_configuration_create(context_t*c,const string_view_t*name,value_t*transport,int32_t has_auth,int32_t auth,const string_view_t*environment_id,int32_t enabled,int32_t required,int32_t parallel,int32_t has_omit,const int32_t*omit,size_t omit_count,int32_t has_startup,double startup,int32_t has_tool_timeout,double tool_timeout,int32_t has_default_approval,int32_t default_approval,int32_t has_enabled,const string_view_t*enabled_tools,size_t enabled_count,int32_t has_disabled,const string_view_t*disabled_tools,size_t disabled_count,int32_t has_scopes,const string_view_t*scopes,size_t scopes_count,int32_t has_oauth,void*oauth,int32_t has_resource,const string_view_t*resource,const string_view_t*tool_keys,void*const*tools,size_t tool_count,void**out){(void)c;(void)auth;(void)omit;(void)startup;(void)tool_timeout;(void)default_approval;(void)enabled_tools;(void)disabled_tools;(void)scopes;(void)oauth;(void)resource;(void)tool_keys;(void)tools;if(transport==NULL||transport->kind!=VALUE_MCP_TRANSPORT)return 1;status_t status=new_typed_value(VALUE_MCP_CONFIGURATION,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),name);copy_view(v->text2,sizeof(v->text2),environment_id);v->flag_a=enabled;v->flag_b=required|(parallel<<1);v->number=(int64_t)(has_auth+has_omit+omit_count+has_startup+has_tool_timeout+has_default_approval+has_enabled+enabled_count+has_disabled+disabled_count+has_scopes+scopes_count+has_oauth+has_resource+tool_count);v->generation=view_equals(name,"server")&&transport->generation==1&&has_auth==0&&view_equals(environment_id,"local")&&enabled==1&&required==0&&parallel==0&&has_omit==0&&omit_count==0&&has_startup==0&&has_tool_timeout==0&&has_default_approval==0&&has_enabled==0&&enabled_count==0&&has_disabled==0&&disabled_count==0&&has_scopes==0&&scopes_count==0&&has_oauth==0&&has_resource==0&&tool_count==0;return 0;}
DESTROY(codex_agent_mcp_server_configuration_destroy)
API status_t codex_agent_mcp_server_create(context_t*c,const string_view_t*name,const string_view_t*display,int32_t auth,value_t*configuration,int32_t origin,int32_t can_remove,void**out){(void)c;status_t status=new_typed_value(VALUE_MCP_SERVER,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),name);copy_view(v->text2,sizeof(v->text2),display);v->flag_a=can_remove;v->flag_b=auth;v->number=origin;v->generation=view_equals(name,"server")&&view_equals(display,"Server")&&(auth==0||auth==2)&&configuration==NULL&&origin==0&&can_remove==1;return 0;}
DESTROY(codex_agent_mcp_server_destroy)

API status_t codex_agent_integration_connector_create(context_t*c,value_t*connector,void**out){(void)c;if(connector==NULL||connector->kind!=VALUE_CONNECTOR)return 1;status_t status=new_typed_value(VALUE_INTEGRATION,0,connector->generation,out);if(status==0){value_t*v=*out;v->flag_a=0;strcpy(v->text,connector->text);}return status;}
API status_t codex_agent_integration_mcp_server_create(context_t*c,value_t*server,void**out){(void)c;if(server==NULL||server->kind!=VALUE_MCP_SERVER)return 1;status_t status=new_typed_value(VALUE_INTEGRATION,0,server->generation,out);if(status==0){value_t*v=*out;v->flag_a=1;v->flag_b=server->flag_b;strcpy(v->text,server->text);}return status;}
DESTROY(codex_agent_integration_connector_destroy)
DESTROY(codex_agent_integration_mcp_server_destroy)
API status_t codex_agent_integration_from_connector(context_t*c,value_t*input,void**out){(void)c;if(input==NULL||input->kind!=VALUE_INTEGRATION||input->flag_a!=0)return 1;status_t status=new_typed_value(VALUE_INTEGRATION,0,0,out);if(status==0)**(value_t**)out=*input;return status;}
API status_t codex_agent_integration_from_mcp_server(context_t*c,value_t*input,void**out){(void)c;if(input==NULL||input->kind!=VALUE_INTEGRATION||input->flag_a!=1)return 1;status_t status=new_typed_value(VALUE_INTEGRATION,0,0,out);if(status==0)**(value_t**)out=*input;return status;}
DESTROY(codex_agent_integration_destroy)
API status_t codex_agent_integration_kind(context_t*c,value_t*v,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_INTEGRATION||out==NULL)return 1;*out=v->generation==1||v->flag_a==1?1:0;return 0;}
API status_t codex_agent_integration_connector(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INTEGRATION||(v->generation==1||v->flag_a==1))return 1;return new_typed_value(VALUE_INTEGRATION,0,0,out);}
API status_t codex_agent_integration_connector_connector(context_t*c,value_t*v,void**out){(void)c;if(v==NULL)return 1;status_t status=new_typed_value(VALUE_CONNECTOR,0,0,out);if(status==0)strcpy(((value_t*)*out)->text,"connector");return status;}
API status_t codex_agent_integration_mcp_server(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INTEGRATION||!(v->generation==1||v->flag_a==1))return 1;return new_typed_value(VALUE_INTEGRATION,0,1,out);}
API status_t codex_agent_integration_mcp_server_server(context_t*c,value_t*v,void**out){(void)c;if(v==NULL)return 1;status_t status=new_typed_value(VALUE_MCP_SERVER,0,0,out);if(status==0){value_t*server=*out;strcpy(server->text,"server");strcpy(server->text2,"Server");server->flag_a=1;server->flag_b=2;}return status;}
API status_t codex_agent_connector_create(context_t*c,const string_view_t*id,const string_view_t*name,const string_view_t*description,int32_t has_url,const string_view_t*url,int32_t accessible,int32_t enabled,const string_view_t*plugins,size_t plugin_count,void**out){(void)c;(void)url;(void)plugins;status_t status=new_typed_value(VALUE_CONNECTOR,0,0,out);if(status!=0)return status;value_t*v=*out;copy_view(v->text,sizeof(v->text),id);v->flag_a=accessible;v->flag_b=enabled;v->number=(int64_t)plugin_count;v->generation=view_equals(id,"connector")&&view_equals(name,"Connector")&&view_equals(description,"")&&has_url==0&&accessible==1&&enabled==1&&plugin_count==0;return 0;}
DESTROY(codex_agent_connector_destroy)
API status_t codex_agent_connector_id_copy(context_t*c,value_t*v,uint8_t*b,size_t n,size_t*r){(void)c;if(v==NULL||v->kind!=VALUE_CONNECTOR)return 1;const char*ids[]={"connector-a","connector-b","connector-a"};return copy_text(v->text[0]=='\0'?ids[v->index%3]:v->text,b,n,r);}
COPY(codex_agent_connector_name_copy,"Connector")
COPY(codex_agent_connector_description_copy,"")
I32(codex_agent_connector_has_install_url,0)
I32(codex_agent_connector_is_accessible,1)
I32(codex_agent_connector_is_enabled,1)
COUNT(codex_agent_connector_plugin_names_count,0)
COPY_AT(codex_agent_connector_plugin_names_copy_at)
API status_t codex_agent_form_text_value_create(context_t*c,const string_view_t*text,void**out){(void)c;status_t status=new_typed_value(VALUE_FORM_TEXT,0,0,out);if(status==0)copy_view(((value_t*)*out)->text,sizeof(((value_t*)*out)->text),text);return status;}
DESTROY(codex_agent_form_text_value_destroy)
API status_t codex_agent_form_value_from_text(context_t*c,value_t*text,void**out){(void)c;if(text==NULL||text->kind!=VALUE_FORM_TEXT)return 1;status_t status=new_typed_value(VALUE_FORM_TEXT,0,0,out);if(status==0)**(value_t**)out=*text;return status;}
DESTROY(codex_agent_form_value_destroy)
API status_t codex_agent_elicitation_response_create(context_t*c,int32_t action,const string_view_t*keys,void*const*values,size_t count,void**out){(void)c;value_t*form=count==0||values==NULL?NULL:values[0];status_t status=new_typed_value(VALUE_ELICITATION_RESPONSE,0,0,out);if(status==0){value_t*v=*out;v->flag_a=action;if(count!=0&&keys!=NULL)copy_view(v->text,sizeof(v->text),&keys[0]);if(form!=NULL)strcpy(v->text2,form->text);v->generation=action==0&&count==1&&keys!=NULL&&view_equals(&keys[0],"answer")&&typed_text(form,VALUE_FORM_TEXT,"yes");}return status;}
DESTROY(codex_agent_elicitation_response_destroy)

#define OP_VALUE(name) API status_t name(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c)return 1;return new_value(out);}
#define OP_COUNT(name,value) API status_t name(context_t*c,operation_t*o,size_t*out){if(o==NULL||o->context!=c||out==NULL)return 1;*out=(value);return 0;}
OP_COUNT(codex_agent_operation_connectors_count,3)
API status_t codex_agent_operation_connector_at(context_t*c,operation_t*o,size_t i,void**out){if(o==NULL||o->context!=c||i>=3)return 1;return new_typed_value(VALUE_CONNECTOR,(int32_t)i,0,out);}
OP_VALUE(codex_agent_operation_hook_catalog)
API status_t codex_agent_operation_hook(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c)return 1;status_t status=new_typed_value(VALUE_HOOK,0,0,out);if(status==0){value_t*v=*out;strcpy(v->text,"hook");strcpy(v->text2,"hooks");v->flag_a=1;v->number=10;}return status;}
OP_COUNT(codex_agent_operation_mcp_servers_count,3)
API status_t codex_agent_operation_mcp_server_at(context_t*c,operation_t*o,size_t i,void**out){if(o==NULL||o->context!=c||i>=3)return 1;return new_typed_value(VALUE_MCP_SERVER,(int32_t)i,0,out);}
API status_t codex_agent_operation_mcp_server(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c)return 1;status_t status=new_typed_value(VALUE_MCP_SERVER,0,0,out);if(status==0){value_t*v=*out;strcpy(v->text,"server");strcpy(v->text2,"Server");v->flag_a=1;v->flag_b=2;}return status;}
OP_COUNT(codex_agent_operation_models_count,3)
API status_t codex_agent_operation_model_at(context_t*c,operation_t*o,size_t i,void**out){if(o==NULL||o->context!=c||i>=3)return 1;return new_typed_value(VALUE_MODEL,(int32_t)i,0,out);}
API status_t codex_agent_operation_model(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c)return 1;status_t status=new_typed_value(VALUE_MODEL,0,0,out);if(status==0)strcpy(((value_t*)*out)->text,"model");return status;}
OP_VALUE(codex_agent_operation_plugin_catalog)
OP_VALUE(codex_agent_operation_plugin_detail)
OP_VALUE(codex_agent_operation_plugin_install_result)
OP_VALUE(codex_agent_operation_skill_catalog)
OP_VALUE(codex_agent_operation_skill_chunk)
API status_t codex_agent_operation_skill(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c)return 1;status_t status=new_typed_value(VALUE_SKILL,0,0,out);if(status==0){value_t*v=*out;strcpy(v->text,"skill");strcpy(v->text2,"skill.md");v->flag_a=1;v->flag_b=1;v->number=110;}return status;}
API status_t codex_agent_operation_string_copy(context_t*c,operation_t*o,uint8_t*b,size_t n,size_t*r){if(o==NULL||o->context!=c)return 1;return copy_text("medium",b,n,r);}
API status_t codex_agent_operation_has_service_tier(context_t*c,operation_t*o,int32_t*out){if(o==NULL||o->context!=c||out==NULL)return 1;*out=atomic_load_explicit(&leaf_service_tier_present,memory_order_acquire);return 0;}
API status_t codex_agent_operation_service_tier(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c)return 1;return new_typed_value(VALUE_SERVICE_TIER,0,0,out);}

COPY(codex_agent_service_tier_id_copy,"fast")
COPY(codex_agent_service_tier_name_copy,"Fast")
COPY(codex_agent_service_tier_description_copy,"fast tier")

API status_t codex_agent_model_id_copy(context_t*c,value_t*v,uint8_t*b,size_t n,size_t*r){(void)c;if(v==NULL||v->kind!=VALUE_MODEL)return 1;const char*ids[]={"model-a","model-b","model-a"};return copy_text(v->text[0]=='\0'?ids[v->index%3]:v->text,b,n,r);}
COPY(codex_agent_model_display_name_copy,"Model")
COPY(codex_agent_model_description_copy,"")
COUNT(codex_agent_model_supported_efforts_count,0)
COPY_AT(codex_agent_model_supported_effort_copy_at)
COPY(codex_agent_model_default_effort_copy,"medium")
I32(codex_agent_model_is_default,1)
COUNT(codex_agent_model_service_tiers_count,0)
CHILD_AT(codex_agent_model_service_tier_at)
I32(codex_agent_model_has_default_service_tier,0)

DESTROY(codex_agent_hook_catalog_destroy)
COUNT(codex_agent_hook_catalog_hooks_count,0)
API status_t codex_agent_hook_catalog_hooks_at(context_t*c,void*v,size_t i,void**out){(void)c;(void)v;(void)i;(void)out;return 13;}
COUNT(codex_agent_hook_catalog_warnings_count,0)
API status_t codex_agent_hook_catalog_warnings_copy_at(context_t*c,void*v,size_t i,uint8_t*b,size_t n,size_t*r){(void)c;(void)v;(void)i;(void)b;(void)n;(void)r;return 13;}
COUNT(codex_agent_hook_catalog_errors_count,0)
API status_t codex_agent_hook_catalog_errors_copy_at(context_t*c,void*v,size_t i,uint8_t*b,size_t n,size_t*r){(void)c;(void)v;(void)i;(void)b;(void)n;(void)r;return 13;}
COPY(codex_agent_hook_key_copy,"hook")
COPY(codex_agent_hook_current_hash_copy,"hash")
I32(codex_agent_hook_is_enabled,1)
COPY(codex_agent_hook_event_name_copy,"afterTurn")
CHILD(codex_agent_hook_handler)
I32(codex_agent_hook_is_managed,0)
COPY(codex_agent_hook_source_copy,"USER")
COPY(codex_agent_hook_source_path_copy,"hooks")
I64(codex_agent_hook_timeout_seconds,10)
I32(codex_agent_hook_trust_status,2)
I32(codex_agent_hook_has_matcher,0)
I32(codex_agent_hook_has_plugin_id,0)
I32(codex_agent_hook_has_status_message,0)
I32(codex_agent_hook_origin,0)
I32(codex_agent_hook_can_uninstall,1)
I32(codex_agent_hook_handler_kind,0)

API status_t codex_agent_mcp_server_name_copy(context_t*c,value_t*v,uint8_t*b,size_t n,size_t*r){(void)c;if(v==NULL||v->kind!=VALUE_MCP_SERVER)return 1;const char*ids[]={"server-a","server-b","server-a"};return copy_text(v->text[0]=='\0'?ids[v->index%3]:v->text,b,n,r);}
COPY(codex_agent_mcp_server_display_name_copy,"Server")
I32(codex_agent_mcp_server_auth_status,0)
I32(codex_agent_mcp_server_has_configuration,0)
I32(codex_agent_mcp_server_origin,0)
I32(codex_agent_mcp_server_can_remove,1)
I32(codex_agent_mcp_server_is_authorized,0)

DESTROY(codex_agent_plugin_catalog_destroy)
COUNT(codex_agent_plugin_catalog_plugins_count,0)
CHILD_AT(codex_agent_plugin_catalog_plugins_at)
COUNT(codex_agent_plugin_catalog_errors_count,0)
COPY_AT(codex_agent_plugin_catalog_errors_copy_at)
I32(codex_agent_plugin_catalog_freshness,0)
DESTROY(codex_agent_plugin_detail_destroy)
CHILD(codex_agent_plugin_detail_summary)
COPY(codex_agent_plugin_detail_description_copy,"detail")
COUNT(codex_agent_plugin_detail_skills_count,0)
CHILD_AT(codex_agent_plugin_detail_skills_at)
COUNT(codex_agent_plugin_detail_connectors_count,0)
CHILD_AT(codex_agent_plugin_detail_connectors_at)
COUNT(codex_agent_plugin_detail_mcp_servers_count,0)
COPY_AT(codex_agent_plugin_detail_mcp_servers_copy_at)
I32(codex_agent_plugin_detail_hook_count,0)
DESTROY(codex_agent_plugin_summary_destroy)
CHILD(codex_agent_plugin_summary_reference)
COPY(codex_agent_plugin_summary_display_name_copy,"Plugin")
COPY(codex_agent_plugin_summary_description_copy,"plugin")
I32(codex_agent_plugin_summary_is_installed,1)
I32(codex_agent_plugin_summary_is_enabled,1)
I32(codex_agent_plugin_summary_install_policy,1)
I32(codex_agent_plugin_summary_auth_policy,0)
I32(codex_agent_plugin_summary_is_available,1)
COUNT(codex_agent_plugin_summary_capabilities_count,0)
COPY_AT(codex_agent_plugin_summary_capabilities_copy_at)
I32(codex_agent_plugin_summary_has_brand_color,0)
I32(codex_agent_plugin_summary_has_privacy_policy_url,0)
I32(codex_agent_plugin_summary_has_terms_of_service_url,0)
I32(codex_agent_plugin_summary_has_website_url,0)
COPY(codex_agent_plugin_reference_id_copy,"plugin-id")
COPY(codex_agent_plugin_reference_name_copy,"plugin")
COPY(codex_agent_plugin_reference_marketplace_name_copy,"market")
I32(codex_agent_plugin_reference_has_marketplace_path,0)
I32(codex_agent_plugin_reference_has_remote_plugin_id,0)
COPY(codex_agent_plugin_reference_uri_copy,"plugin://plugin@market")
DESTROY(codex_agent_plugin_install_result_destroy)
I32(codex_agent_plugin_install_result_auth_policy,0)
COUNT(codex_agent_plugin_install_result_connectors_count,0)
CHILD_AT(codex_agent_plugin_install_result_connectors_at)
I32(codex_agent_plugin_install_result_has_message,0)

DESTROY(codex_agent_skill_catalog_destroy)
COUNT(codex_agent_skill_catalog_skills_count,0)
CHILD_AT(codex_agent_skill_catalog_skills_at)
COUNT(codex_agent_skill_catalog_errors_count,0)
COPY_AT(codex_agent_skill_catalog_errors_copy_at)
DESTROY(codex_agent_skill_chunk_destroy)
COPY(codex_agent_skill_chunk_content_copy,"content")
API status_t codex_agent_skill_chunk_next_offset(context_t*c,void*v,int32_t*has,int64_t*out){(void)c;if(v==NULL||has==NULL||out==NULL)return 1;*has=0;*out=0;return 0;}
I64(codex_agent_skill_chunk_total_bytes,7)
COPY(codex_agent_skill_name_copy,"skill")
COPY(codex_agent_skill_display_name_copy,"Skill")
COPY(codex_agent_skill_description_copy,"skill")
COPY(codex_agent_skill_path_copy,"skill.md")
I32(codex_agent_skill_scope,0)
I32(codex_agent_skill_is_enabled,1)
I32(codex_agent_skill_has_brand_color,0)
COUNT(codex_agent_skill_dependencies_count,0)
COPY_AT(codex_agent_skill_dependencies_copy_at)
I32(codex_agent_skill_can_uninstall,1)
I32(codex_agent_skill_origin,0)

/* Exact native-backed CodexConversations/CodexConversation test surface. */
static status_t conversation_catalog_operation(context_t *c, int32_t marker, operation_callback_t cb, void *u, operation_t **out) {
    status_t status = start_threaded_operation(c, cb, u, out);
    if (status == 0) (*out)->conversation_id = marker;
    return status;
}

API status_t codex_agent_conversations_list(context_t*c,conversations_t*s,operation_callback_t cb,void*u,operation_t**out){if(s==NULL||s->context!=c)return 5;return conversation_catalog_operation(c,101,cb,u,out);}
API status_t codex_agent_conversations_read(context_t*c,conversations_t*s,value_t*id,operation_callback_t cb,void*u,operation_t**out){if(s==NULL||s->context!=c||!typed_text(id,VALUE_CONVERSATION_ID,"read-input"))return 1;return conversation_catalog_operation(c,102,cb,u,out);}
API status_t codex_agent_conversations_rename(context_t*c,conversations_t*s,value_t*id,const string_view_t*name,operation_callback_t cb,void*u,operation_t**out){if(s==NULL||s->context!=c||!typed_text(id,VALUE_CONVERSATION_ID,"rename-input")||!view_equals(name,"Renamed"))return 1;return conversation_catalog_operation(c,103,cb,u,out);}
API status_t codex_agent_conversations_delete(context_t*c,conversations_t*s,value_t*id,operation_callback_t cb,void*u,operation_t**out){if(s==NULL||s->context!=c||!typed_text(id,VALUE_CONVERSATION_ID,"delete-input"))return 1;return conversation_catalog_operation(c,104,cb,u,out);}

API status_t codex_agent_operation_conversation_summaries_count(context_t*c,operation_t*o,size_t*out){if(o==NULL||o->context!=c||o->conversation_id!=101||out==NULL)return 1;*out=3;return 0;}
API status_t codex_agent_operation_conversation_summary_at(context_t*c,operation_t*o,size_t i,void**out){if(o==NULL||o->context!=c||o->conversation_id!=101||i>=3)return 1;return new_typed_value(VALUE_CONVERSATION_SUMMARY,(int32_t)(i==1?1:0),0,out);}
API status_t codex_agent_operation_conversation_value(context_t*c,operation_t*o,void**out){if(o==NULL||o->context!=c||o->conversation_id!=102)return 1;return new_typed_value(VALUE_CONVERSATION_VALUE,0,0,out);}

DESTROY(codex_agent_conversation_summary_destroy)
API status_t codex_agent_conversation_summary_conversation_id(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_CONVERSATION_SUMMARY)return 1;status_t s=new_typed_value(VALUE_CONVERSATION_ID,v->index,0,out);if(s==0)strcpy(((value_t*)*out)->text,v->index==1?"conversation-beta":"conversation-alpha");return s;}
API status_t codex_agent_conversation_summary_title_copy(context_t*c,value_t*v,uint8_t*b,size_t n,size_t*r){(void)c;if(v==NULL||v->kind!=VALUE_CONVERSATION_SUMMARY)return 1;return copy_text(v->index==1?"Beta":"Alpha",b,n,r);}
API status_t codex_agent_conversation_summary_updated_at_epoch_seconds(context_t*c,value_t*v,int64_t*out){(void)c;if(v==NULL||v->kind!=VALUE_CONVERSATION_SUMMARY||out==NULL)return 1;*out=v->index==1?22:11;return 0;}

DESTROY(codex_agent_conversation_value_destroy)
API status_t codex_agent_conversation_value_summary(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_CONVERSATION_VALUE)return 1;return new_typed_value(VALUE_CONVERSATION_SUMMARY,0,0,out);}
API status_t codex_agent_conversation_value_messages_count(context_t*c,value_t*v,size_t*out){(void)c;if(v==NULL||v->kind!=VALUE_CONVERSATION_VALUE||out==NULL)return 1;*out=3;return 0;}
API status_t codex_agent_conversation_value_message_at(context_t*c,value_t*v,size_t i,void**out){(void)c;if(v==NULL||v->kind!=VALUE_CONVERSATION_VALUE||i>=3)return 1;return new_typed_value(VALUE_MESSAGE,(int32_t)(i==1?1:0),0,out);}

static const char *conversation_message_text(value_t*v,const char*a,const char*b,const char*g,const char*d){return v->index==1?b:v->index==2?g:v->index==3?d:a;}
DESTROY(codex_agent_message_destroy)
#define CONVERSATION_MESSAGE_COPY(name,a,b,g,d) API status_t name(context_t*c,value_t*v,uint8_t*out,size_t n,size_t*r){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE)return 1;return copy_text(conversation_message_text(v,a,b,g,d),out,n,r);}
CONVERSATION_MESSAGE_COPY(codex_agent_message_id_copy,"message-alpha","message-beta","message-gamma","message-delta")
CONVERSATION_MESSAGE_COPY(codex_agent_message_client_message_id_copy,"client-alpha","client-beta","client-gamma","client-delta")
CONVERSATION_MESSAGE_COPY(codex_agent_message_text_copy,"hello-alpha","hello-beta","hello-gamma","hello-delta")
CONVERSATION_MESSAGE_COPY(codex_agent_message_reasoning_copy,"reason-alpha","reason-beta","reason-gamma","reason-delta")
CONVERSATION_MESSAGE_COPY(codex_agent_message_plan_copy,"plan-alpha","plan-beta","plan-gamma","plan-delta")
CONVERSATION_MESSAGE_COPY(codex_agent_message_shell_command_copy,"pwd-alpha","pwd-beta","pwd-gamma","pwd-delta")
#undef CONVERSATION_MESSAGE_COPY
API status_t codex_agent_message_has_client_message_id(context_t*c,value_t*v,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||out==NULL)return 1;*out=v->index%2==0;return 0;}
API status_t codex_agent_message_has_reasoning(context_t*c,value_t*v,int32_t*out){return codex_agent_message_has_client_message_id(c,v,out);}
API status_t codex_agent_message_has_plan(context_t*c,value_t*v,int32_t*out){return codex_agent_message_has_client_message_id(c,v,out);}
API status_t codex_agent_message_has_shell_command(context_t*c,value_t*v,int32_t*out){return codex_agent_message_has_client_message_id(c,v,out);}
API status_t codex_agent_message_role(context_t*c,value_t*v,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||out==NULL)return 1;*out=1;return 0;}
API status_t codex_agent_message_collaboration_mode(context_t*c,value_t*v,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||out==NULL)return 1;*out=1;return 0;}
API status_t codex_agent_message_exit_code(context_t*c,value_t*v,int32_t*has,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||has==NULL||out==NULL)return 1;*has=v->index%2==0;*out=v->index==2?9:7;return 0;}
API status_t codex_agent_message_capabilities_count(context_t*c,value_t*v,size_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||out==NULL)return 1;*out=v->index%2==0?1:0;return 0;}
API status_t codex_agent_message_has_capability(context_t*c,value_t*v,int32_t capability,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||out==NULL)return 1;*out=v->index%2==0&&capability==0;return 0;}
API status_t codex_agent_message_invocations_count(context_t*c,value_t*v,size_t*out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||out==NULL)return 1;*out=v->index%2==0?2:0;return 0;}
API status_t codex_agent_message_invocation_at(context_t*c,value_t*v,size_t i,void**out){(void)c;if(v==NULL||v->kind!=VALUE_MESSAGE||v->index%2!=0||i>=2)return 1;return new_typed_value(VALUE_INVOCATION,(int32_t)i,1,out);}

DESTROY(codex_agent_invocation_destroy)
API status_t codex_agent_invocation_kind(context_t*c,value_t*v,int32_t*out){(void)c;if(v==NULL||v->kind!=VALUE_INVOCATION||out==NULL)return 1;*out=v->index;return 0;}
API status_t codex_agent_invocation_plugin(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INVOCATION||v->index!=0)return 1;return new_typed_value(VALUE_INVOCATION_PLUGIN,0,v->generation,out);}
API status_t codex_agent_invocation_skill(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INVOCATION||v->index!=1)return 1;return new_typed_value(VALUE_INVOCATION_SKILL,1,v->generation,out);}
API status_t codex_agent_invocation_plugin_create(context_t*c,const string_view_t*n,const string_view_t*u,void**out){(void)c;status_t s=new_typed_value(VALUE_INVOCATION_PLUGIN,0,view_equals(n,"plugin")&&view_equals(u,"plugin://plugin@market"),out);return s;}
API status_t codex_agent_invocation_skill_create(context_t*c,const string_view_t*n,const string_view_t*p,void**out){(void)c;status_t s=new_typed_value(VALUE_INVOCATION_SKILL,1,view_equals(n,"skill")&&view_equals(p,"skill.md"),out);return s;}
DESTROY(codex_agent_invocation_plugin_destroy)
DESTROY(codex_agent_invocation_skill_destroy)
COPY(codex_agent_invocation_plugin_name_copy,"plugin")
COPY(codex_agent_invocation_plugin_uri_copy,"plugin://plugin@market")
COPY(codex_agent_invocation_skill_name_copy,"skill")
COPY(codex_agent_invocation_skill_path_copy,"skill.md")
API status_t codex_agent_invocation_from_plugin(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INVOCATION_PLUGIN)return 1;return new_typed_value(VALUE_INVOCATION,0,v->generation,out);}
API status_t codex_agent_invocation_from_skill(context_t*c,value_t*v,void**out){(void)c;if(v==NULL||v->kind!=VALUE_INVOCATION_SKILL)return 1;return new_typed_value(VALUE_INVOCATION,1,v->generation,out);}

API status_t codex_agent_turn_request_create(context_t*c,const string_view_t*prompt,int32_t has_client,const string_view_t*client,int32_t has_model,const string_view_t*model,int32_t has_effort,const string_view_t*effort,int32_t has_tier,const string_view_t*tier,int32_t approval,const int32_t*capabilities,size_t capability_count,value_t*const*invocations,size_t invocation_count,int32_t collaboration,void**out){(void)c;status_t s=new_typed_value(VALUE_TURN_REQUEST,0,0,out);if(s!=0)return s;value_t*v=*out;v->generation=view_equals(prompt,"structured")&&has_client==1&&view_equals(client,"client-1")&&has_model==1&&view_equals(model,"model")&&has_effort==1&&view_equals(effort,"high")&&has_tier==1&&view_equals(tier,"fast")&&approval==2&&capability_count==1&&capabilities!=NULL&&capabilities[0]==0&&invocation_count==2&&invocations!=NULL&&invocations[0]!=NULL&&invocations[1]!=NULL&&invocations[0]->index==0&&invocations[0]->generation==1&&invocations[1]->index==1&&invocations[1]->generation==1&&collaboration==1;return 0;}
DESTROY(codex_agent_turn_request_destroy)
API status_t codex_agent_conversation_send_request(context_t*c,conversation_t*v,value_t*r,operation_callback_t cb,void*u,operation_t**out){if(v==NULL||v->context!=c||r==NULL||r->kind!=VALUE_TURN_REQUEST||r->generation!=1)return 1;return start_threaded_operation(c,cb,u,out);}

static status_t conversation_projection_get(conversation_t*v,int32_t current,snapshot_t**out){if(v==NULL||out==NULL||*out!=NULL)return 1;*out=new_snapshot(SNAPSHOT_CONVERSATION,current,v);return 0;}
static status_t conversation_projection_subscribe(context_t*c,conversation_t*v,int32_t current,int32_t subsequent,state_callback_t cb,void*u,subscription_t**out){if(c==NULL||v==NULL||v->context!=c||cb==NULL||out==NULL||*out!=NULL)return 1;subscription_t*s=calloc(1,sizeof(*s));s->context=c;s->callback=cb;s->user_data=u;s->owner=v;atomic_init(&s->destroy_attempts,0);*out=s;cb(c,s,0,new_snapshot(SNAPSHOT_CONVERSATION,current,v),0,u);if(atomic_load_explicit(&conversation_test_terminal,memory_order_acquire)){cb(c,s,0,new_snapshot(SNAPSHOT_CONVERSATION,subsequent,v),0,u);cb(c,s,0,NULL,1,u);}else atomic_store_explicit(&conversation_subscription,s,memory_order_release);return 0;}
#define CONVERSATION_PROJECTION(name,current,subsequent) API status_t codex_agent_conversation_##name##_get(context_t*c,conversation_t*v,snapshot_t**out){(void)c;return conversation_projection_get(v,current,out);} API status_t codex_agent_conversation_##name##_subscribe(context_t*c,conversation_t*v,state_callback_t cb,void*u,subscription_t**out){return conversation_projection_subscribe(c,v,current,subsequent,cb,u,out);}
CONVERSATION_PROJECTION(current_messages,50,51)
CONVERSATION_PROJECTION(active_turn_progress,60,61)
CONVERSATION_PROJECTION(can_start_turn,0,1)
CONVERSATION_PROJECTION(can_reload,0,1)
CONVERSATION_PROJECTION(can_cancel_turn,0,1)
CONVERSATION_PROJECTION(can_run_shell_command,0,1)
CONVERSATION_PROJECTION(is_turn_active,0,1)
#undef CONVERSATION_PROJECTION
API status_t codex_agent_conversation_current_messages_count(context_t*c,snapshot_t*s,size_t*out){(void)c;if(s==NULL||out==NULL||(s->value!=50&&s->value!=51))return 1;*out=3;return 0;}
API status_t codex_agent_conversation_current_messages_at(context_t*c,snapshot_t*s,size_t i,void**out){(void)c;if(s==NULL||i>=3||(s->value!=50&&s->value!=51))return 1;int base=s->value==50?0:2;return new_typed_value(VALUE_MESSAGE,(int32_t)(i==1?base+1:base),0,out);}
API status_t codex_agent_conversation_active_turn_progress_has_value(context_t*c,snapshot_t*s,int32_t*out){(void)c;if(s==NULL||out==NULL||(s->value!=60&&s->value!=61))return 1;*out=s->value==60;return 0;}
API status_t codex_agent_conversation_active_turn_progress_value(context_t*c,snapshot_t*s,void**out){(void)c;if(s==NULL||s->value!=60)return 1;return new_typed_value(VALUE_TURN_PROGRESS,0,0,out);}

DESTROY(codex_agent_turn_progress_destroy)
COPY(codex_agent_turn_progress_text_copy,"working")
COPY(codex_agent_turn_progress_commentary_copy,"commentary")
COPY(codex_agent_turn_progress_reasoning_copy,"reasoning")
COPY(codex_agent_turn_progress_plan_copy,"plan")
COPY(codex_agent_turn_progress_shell_output_copy,"output")
I32(codex_agent_turn_progress_has_plan_progress,0)
API status_t codex_agent_turn_progress_shell_exit_code(context_t*c,value_t*v,int32_t*has,int32_t*out){(void)c;if(v==NULL||has==NULL||out==NULL)return 1;*has=1;*out=0;return 0;}
API status_t codex_agent_turn_progress_work_activity(context_t*c,value_t*v,int32_t*has,int32_t*out){(void)c;if(v==NULL||has==NULL||out==NULL)return 1;*has=1;*out=1;return 0;}
COUNT(codex_agent_turn_progress_hook_activities_count,0)
CHILD_AT(codex_agent_turn_progress_hook_activity_at)
I32(codex_agent_turn_progress_is_truncated,1)
