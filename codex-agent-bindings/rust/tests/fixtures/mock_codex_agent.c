#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>
#include <time.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

#if defined(__APPLE__) && defined(__aarch64__)
#define CODEX_AGENT_TEST_TARGET "macos-arm64"
#elif defined(__APPLE__) && defined(__x86_64__)
#define CODEX_AGENT_TEST_TARGET "macos-x64"
#elif defined(__linux__) && defined(__aarch64__)
#define CODEX_AGENT_TEST_TARGET "linux-arm64"
#elif defined(__linux__) && defined(__x86_64__)
#define CODEX_AGENT_TEST_TARGET "linux-x64"
#elif defined(_WIN32) && defined(_M_X64)
#define CODEX_AGENT_TEST_TARGET "windows-x64"
#else
#define CODEX_AGENT_TEST_TARGET "unsupported"
#endif
#ifndef CODEX_AGENT_TEST_COMPONENT_ID
#define CODEX_AGENT_TEST_COMPONENT_ID "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
#endif
#ifndef CODEX_AGENT_TEST_ACTUAL_ABI
#define CODEX_AGENT_TEST_ACTUAL_ABI ((1u << 24) | (13u << 16))
#endif
#ifndef CODEX_AGENT_TEST_CONTEXT_CREATE_STATUS
#define CODEX_AGENT_TEST_CONTEXT_CREATE_STATUS 0
#endif

typedef int32_t status_t;
typedef struct context context_t;
typedef struct host host_t;
typedef struct agent agent_t;
typedef struct conversations conversations_t;
typedef struct conversation conversation_t;
typedef struct operation operation_t;
typedef struct subscription subscription_t;
typedef struct snapshot snapshot_t;
typedef struct failure failure_t;
typedef void (*operation_callback_t)(context_t *, operation_t *, void *);
typedef void (*state_callback_t)(context_t *, subscription_t *, status_t, snapshot_t *, int32_t, void *);

typedef struct { const uint8_t *data; size_t size; } string_view_t;
typedef struct {
    uint32_t struct_size;
    string_view_t name;
    string_view_t title;
    string_view_t version;
} client_info_t;
typedef struct {
    uint32_t struct_size;
    string_view_t bundle_directory;
    string_view_t data_directory;
    client_info_t client_info;
} host_options_t;
typedef struct { uint32_t struct_size; string_view_t path; } workspace_selection_t;
typedef struct {
    uint32_t struct_size;
    int32_t has_conversation_id;
    string_view_t conversation_id;
    int32_t has_approval_preset;
    int32_t approval_preset;
    int32_t has_service_tier;
    string_view_t service_tier;
} conversation_open_options_t;

struct context { context_t **original_slot; _Atomic int32_t destroy_attempts; };
struct host { context_t *context; int32_t state; _Atomic int32_t release_attempts; };
struct agent { context_t *context; host_t *host; _Atomic int32_t release_attempts; };
struct conversations { context_t *context; agent_t *agent; int32_t active_id; _Atomic int32_t release_attempts; };
struct conversation { context_t *context; int32_t id; int32_t state; _Atomic int32_t release_attempts; };
struct failure { char *code; char *message; int32_t recoverable; _Atomic int32_t release_attempts; };
struct operation {
    context_t *context;
    operation_callback_t callback;
    void *user_data;
    _Atomic int32_t result;
    int32_t conversation_id;
    _Atomic int32_t complete;
    _Atomic int32_t callback_sent;
    _Atomic int32_t callback_active;
    _Atomic int32_t worker_done;
    _Atomic int32_t destroy_attempts;
};
enum snapshot_kind { SNAPSHOT_HOST, SNAPSHOT_ACTIVE, SNAPSHOT_CONVERSATION };
struct snapshot {
    enum snapshot_kind kind;
    int32_t value;
    void *owner;
};
struct subscription {
    context_t *context;
    state_callback_t callback;
    void *user_data;
    enum snapshot_kind kind;
    void *owner;
    _Atomic int32_t destroy_attempts;
};

static _Atomic(subscription_t *) host_subscription = NULL;
static _Atomic(subscription_t *) conversation_subscription = NULL;
static _Atomic int32_t conversation_test_mode = 0;
static _Atomic int32_t conversation_test_terminal = 1;
static _Atomic int32_t next_conversation_id = 40;
static _Atomic int32_t context_destroy_errors = 0;
static _Atomic int32_t operation_destroy_count = 0;
static _Atomic int32_t subscription_destroy_count = 0;
static _Atomic int32_t abi_compatible = 1;
static _Atomic int32_t identity_mode = 0;
static _Atomic int32_t operation_destroy_mode = 0;
static _Atomic int32_t subscription_destroy_mode = 0;
static _Atomic int32_t owned_release_mode = 0;
static _Atomic int32_t failure_release_mode = 0;
static _Atomic int32_t context_destroy_mode = 0;
static _Atomic int32_t last_open_has_conversation_id = -1;
static _Atomic int32_t last_open_conversation_id_size = -1;
static _Atomic int32_t last_open_has_service_tier = -1;
static _Atomic int32_t last_open_service_tier_size = -1;
static _Atomic int32_t host_workspace_available = 1;
static _Atomic int32_t closed_conversation_id = 0;
static _Atomic int32_t agent_children_live = 0;
static _Atomic int32_t agent_release_with_live_children_errors = 0;
static _Atomic int32_t host_operation_result = 0;
static _Atomic int32_t host_operation_completion_mode = 1;
static _Atomic int32_t require_exact_host_inputs = 0;
static char copied_host_options[5][128];
static char copied_workspace_selection[128];
static char release_log[128];
static size_t release_log_size = 0;
static pthread_mutex_t release_log_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t host_subscription_mutex = PTHREAD_MUTEX_INITIALIZER;

static void log_release(char value) {
    pthread_mutex_lock(&release_log_mutex);
    if (release_log_size + 1 < sizeof(release_log)) {
        release_log[release_log_size++] = value;
        release_log[release_log_size] = '\0';
    }
    pthread_mutex_unlock(&release_log_mutex);
}

static status_t cleanup_status(_Atomic int32_t *attempts, _Atomic int32_t *mode) {
    int32_t selected = atomic_load_explicit(mode, memory_order_acquire);
    int32_t attempt = atomic_fetch_add_explicit(attempts, 1, memory_order_acq_rel);
    if (selected == 1) return 6;
    if (selected == 2) return 8;
    return attempt == 0 ? 6 : 0;
}

static status_t copy_text(const char *text, uint8_t *buffer, size_t capacity, size_t *required) {
    size_t size = strlen(text);
    if (required == NULL) return 1;
    *required = size;
    if (capacity < size) return 9;
    if (size != 0 && buffer == NULL) return 1;
    if (size != 0) memcpy(buffer, text, size);
    return 0;
}

static snapshot_t *new_snapshot(enum snapshot_kind kind, int32_t value, void *owner) {
    snapshot_t *snapshot = (snapshot_t *)calloc(1, sizeof(snapshot_t));
    snapshot->kind = kind;
    snapshot->value = value;
    snapshot->owner = owner;
    return snapshot;
}

static status_t start_operation(
    context_t *context,
    int32_t result,
    int32_t conversation_id,
    int32_t completion_mode,
    operation_callback_t callback,
    void *user_data,
    operation_t **out_operation) {
    if (context == NULL || callback == NULL || out_operation == NULL || *out_operation != NULL) return 1;
    operation_t *operation = (operation_t *)calloc(1, sizeof(operation_t));
    operation->context = context;
    operation->callback = callback;
    operation->user_data = user_data;
    atomic_init(&operation->result, result);
    operation->conversation_id = conversation_id;
    atomic_init(&operation->complete, 0);
    atomic_init(&operation->callback_sent, 0);
    atomic_init(&operation->callback_active, 0);
    atomic_init(&operation->worker_done, completion_mode == 2 ? 0 : 1);
    atomic_init(&operation->destroy_attempts, 0);
    *out_operation = operation;
    if (completion_mode == 1) {
        atomic_store_explicit(&operation->callback_sent, 1, memory_order_release);
        atomic_store_explicit(&operation->callback_active, 1, memory_order_release);
        atomic_store_explicit(&operation->complete, 1, memory_order_release);
        callback(context, operation, user_data);
        atomic_store_explicit(&operation->callback_active, 0, memory_order_release);
    }
    return 0;
}

static void *complete_operation_on_worker(void *value) {
    operation_t *operation = (operation_t *)value;
    struct timespec delay = { .tv_sec = 0, .tv_nsec = 5000000 };
    nanosleep(&delay, NULL);
    if (atomic_exchange_explicit(&operation->callback_sent, 1, memory_order_acq_rel) == 0) {
        atomic_store_explicit(&operation->callback_active, 1, memory_order_release);
        atomic_store_explicit(&operation->complete, 1, memory_order_release);
        operation->callback(operation->context, operation, operation->user_data);
        atomic_store_explicit(&operation->callback_active, 0, memory_order_release);
    }
    atomic_store_explicit(&operation->worker_done, 1, memory_order_release);
    return NULL;
}

static status_t start_threaded_operation(
    context_t *context,
    operation_callback_t callback,
    void *user_data,
    operation_t **out_operation) {
    status_t status = start_operation(context, 0, 0, 2, callback, user_data, out_operation);
    if (status != 0) return status;
    pthread_t worker;
    if (pthread_create(&worker, NULL, complete_operation_on_worker, *out_operation) != 0) return 8;
    pthread_detach(worker);
    return 0;
}

API uint32_t codex_agent_abi_version(void) { return CODEX_AGENT_TEST_ACTUAL_ABI; }
API int32_t codex_agent_abi_is_compatible(uint32_t requested) {
    return atomic_load_explicit(&abi_compatible, memory_order_acquire) &&
        (requested >> 24) == 1u && requested <= codex_agent_abi_version();
}

#ifndef CODEX_AGENT_TEST_OMIT_IDENTITY
API status_t codex_agent_runtime_identity(char *buffer, size_t *inout_size) {
    static const char valid[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.13.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
        "\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"" CODEX_AGENT_TEST_TARGET "\"}";
    static const char schema[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.13.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
        "\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":2,\"target\":\"" CODEX_AGENT_TEST_TARGET "\"}";
    static const char wrong_target[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.13.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
        "\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"wrong-target\"}";
    static const char wrong_contract[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.13.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\","
        "\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"" CODEX_AGENT_TEST_TARGET "\"}";
    static const char old_abi[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.12.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
        "\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"" CODEX_AGENT_TEST_TARGET "\"}";
    static const char incompatible_runtime[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.13.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
        "\"runtimeCompatibilityVersion\":\"0.3.0\",\"schemaVersion\":1,\"target\":\"" CODEX_AGENT_TEST_TARGET "\"}";
    static const char above_actual_abi[] =
        "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\","
        "\"cAbiVersion\":\"1.14.0\",\"componentId\":\"" CODEX_AGENT_TEST_COMPONENT_ID "\","
        "\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
        "\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
        "\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"" CODEX_AGENT_TEST_TARGET "\"}";
    const char *identity = valid;
    switch (atomic_load(&identity_mode)) {
        case 1: identity = schema; break;
        case 2: identity = wrong_target; break;
        case 3: identity = wrong_contract; break;
        case 4: identity = old_abi; break;
        case 5: identity = incompatible_runtime; break;
        case 6: identity = "not-json"; break;
        case 7: identity = above_actual_abi; break;
        default: break;
    }
    if (inout_size == NULL) return 1;
    const size_t required = strlen(identity) + 1u;
    const size_t capacity = *inout_size;
    *inout_size = required;
    if (buffer == NULL || capacity < required) return 9;
    memcpy(buffer, identity, required);
    return 0;
}
#endif

API status_t codex_agent_context_create(context_t **out_context) {
    if (CODEX_AGENT_TEST_CONTEXT_CREATE_STATUS != 0) return CODEX_AGENT_TEST_CONTEXT_CREATE_STATUS;
    if (out_context == NULL || *out_context != NULL) return 1;
    context_t *context = (context_t *)calloc(1, sizeof(context_t));
    context->original_slot = out_context;
    atomic_init(&context->destroy_attempts, 0);
    *out_context = context;
    return 0;
}

API status_t codex_agent_context_destroy(context_t **context) {
    if (context == NULL || *context == NULL) return 0;
    if ((*context)->original_slot != context) {
        atomic_fetch_add_explicit(&context_destroy_errors, 1, memory_order_acq_rel);
        return 1;
    }
    status_t status = cleanup_status(&(*context)->destroy_attempts, &context_destroy_mode);
    if (status != 0) return status;
    free(*context);
    *context = NULL;
    log_release('X');
    return 0;
}

static void host_copy_view(char *out, size_t capacity, const string_view_t *value) {
    size_t size = value == NULL ? 0 : value->size;
    if (size >= capacity) size = capacity - 1;
    if (size != 0 && value->data != NULL) memcpy(out, value->data, size);
    out[size] = '\0';
}

static int host_view_equals(const string_view_t *value, const char *expected) {
    size_t size = strlen(expected);
    return value != NULL && value->size == size &&
        (size == 0 || (value->data != NULL && memcmp(value->data, expected, size) == 0));
}

API status_t codex_agent_host_create(context_t *context, const host_options_t *options, host_t **out_host) {
    if (context == NULL || options == NULL || out_host == NULL || *out_host != NULL) return 1;
    if (options->struct_size != sizeof(host_options_t) || options->client_info.struct_size != sizeof(client_info_t)) return 1;
    const string_view_t *views[] = {
        &options->bundle_directory,
        &options->data_directory,
        &options->client_info.name,
        &options->client_info.title,
        &options->client_info.version,
    };
    for (int32_t index = 0; index < 5; index++) {
        host_copy_view(copied_host_options[index], sizeof(copied_host_options[index]), views[index]);
    }
    if (atomic_load_explicit(&require_exact_host_inputs, memory_order_acquire) != 0) {
        const char *expected[] = {
            "/host-bundle", "/host-data", "host-client", "Host Client", "1.0"
        };
        for (int32_t index = 0; index < 5; index++) {
            if (!host_view_equals(views[index], expected[index])) return 1;
        }
    }
    host_t *host = (host_t *)calloc(1, sizeof(host_t));
    host->context = context;
    host->state = 0;
    atomic_init(&host->release_attempts, 0);
    *out_host = host;
    return 0;
}

API status_t codex_agent_host_release(context_t *context, host_t **host) {
    if (host == NULL || *host == NULL) return 0;
    if ((*host)->context != context) return 5;
    if (atomic_load_explicit(&owned_release_mode, memory_order_acquire) == 0 &&
        (*host)->state != 6) return 6;
    status_t status = cleanup_status(&(*host)->release_attempts, &owned_release_mode);
    if (status != 0) return status;
    free(*host);
    *host = NULL;
    log_release('H');
    return 0;
}

API status_t codex_agent_host_start(context_t *context, host_t *host, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (host == NULL || host->context != context) return 5;
    int32_t result = atomic_load_explicit(&host_operation_result, memory_order_acquire);
    int32_t completion = atomic_load_explicit(&host_operation_completion_mode, memory_order_acquire);
    if (result == 0 && completion == 1) host->state = 4;
    return start_operation(context, result, 0, completion, callback, user_data, out_operation);
}

API status_t codex_agent_host_select_workspace(context_t *context, host_t *host, const workspace_selection_t *selection, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (host == NULL || host->context != context || selection == NULL || selection->struct_size != sizeof(workspace_selection_t)) return 1;
    host_copy_view(copied_workspace_selection, sizeof(copied_workspace_selection), &selection->path);
    if (atomic_load_explicit(&require_exact_host_inputs, memory_order_acquire) != 0 &&
        !host_view_equals(&selection->path, "/selected-workspace")) return 1;
    return start_operation(
        context,
        atomic_load_explicit(&host_operation_result, memory_order_acquire),
        0,
        atomic_load_explicit(&host_operation_completion_mode, memory_order_acquire),
        callback,
        user_data,
        out_operation);
}

API status_t codex_agent_host_close(context_t *context, host_t *host, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (host == NULL || host->context != context) return 5;
    int32_t result = atomic_load_explicit(&host_operation_result, memory_order_acquire);
    if (result == 0 &&
        atomic_load_explicit(&host_operation_completion_mode, memory_order_acquire) == 1) host->state = 6;
    return start_operation(
        context,
        result,
        0,
        atomic_load_explicit(&host_operation_completion_mode, memory_order_acquire),
        callback,
        user_data,
        out_operation);
}

API status_t codex_agent_host_state_get(context_t *context, host_t *host, snapshot_t **out_snapshot) {
    if (host == NULL || host->context != context || out_snapshot == NULL || *out_snapshot != NULL) return 1;
    *out_snapshot = new_snapshot(SNAPSHOT_HOST, host->state, host);
    return 0;
}

API status_t codex_agent_host_state_subscribe(context_t *context, host_t *host, state_callback_t callback, void *user_data, subscription_t **out_subscription) {
    if (host == NULL || host->context != context || callback == NULL || out_subscription == NULL || *out_subscription != NULL) return 1;
    subscription_t *subscription = (subscription_t *)calloc(1, sizeof(subscription_t));
    subscription->context = context;
    subscription->callback = callback;
    subscription->user_data = user_data;
    subscription->kind = SNAPSHOT_HOST;
    subscription->owner = host;
    atomic_init(&subscription->destroy_attempts, 0);
    *out_subscription = subscription;
    pthread_mutex_lock(&host_subscription_mutex);
    atomic_store_explicit(&host_subscription, subscription, memory_order_release);
    pthread_mutex_unlock(&host_subscription_mutex);
    callback(context, subscription, 0, new_snapshot(SNAPSHOT_HOST, host->state, host), 0, user_data);
    return 0;
}

API status_t codex_agent_agent_release(context_t *context, agent_t **agent) {
    if (agent == NULL || *agent == NULL) return 0;
    if ((*agent)->context != context) return 5;
    if (atomic_load_explicit(&agent_children_live, memory_order_acquire) != 0) {
        atomic_fetch_add_explicit(&agent_release_with_live_children_errors, 1, memory_order_acq_rel);
        return 6;
    }
    status_t status = cleanup_status(&(*agent)->release_attempts, &owned_release_mode);
    if (status != 0) return status;
    free(*agent);
    *agent = NULL;
    log_release('A');
    return 0;
}

API status_t codex_agent_agent_conversations(context_t *context, agent_t *agent, conversations_t **out_conversations) {
    if (agent == NULL || agent->context != context || out_conversations == NULL || *out_conversations != NULL) return 1;
    conversations_t *value = (conversations_t *)calloc(1, sizeof(conversations_t));
    value->context = context;
    value->agent = agent;
    atomic_init(&value->release_attempts, 0);
    *out_conversations = value;
    atomic_fetch_add_explicit(&agent_children_live, 1, memory_order_acq_rel);
    return 0;
}

API status_t codex_agent_conversations_release(context_t *context, conversations_t **conversations) {
    if (conversations == NULL || *conversations == NULL) return 0;
    if ((*conversations)->context != context) return 5;
    status_t status = cleanup_status(&(*conversations)->release_attempts, &owned_release_mode);
    if (status != 0) return status;
    free(*conversations);
    *conversations = NULL;
    atomic_fetch_sub_explicit(&agent_children_live, 1, memory_order_acq_rel);
    log_release('S');
    return 0;
}

API status_t codex_agent_conversations_active_get(context_t *context, conversations_t *conversations, snapshot_t **out_snapshot) {
    if (conversations == NULL || conversations->context != context || out_snapshot == NULL || *out_snapshot != NULL) return 1;
    *out_snapshot = new_snapshot(SNAPSHOT_ACTIVE, conversations->active_id, conversations);
    return 0;
}

API status_t codex_agent_conversations_active_subscribe(context_t *context, conversations_t *conversations, state_callback_t callback, void *user_data, subscription_t **out_subscription) {
    if (conversations == NULL || conversations->context != context || callback == NULL || out_subscription == NULL || *out_subscription != NULL) return 1;
    subscription_t *subscription = (subscription_t *)calloc(1, sizeof(subscription_t));
    subscription->context = context;
    subscription->callback = callback;
    subscription->user_data = user_data;
    subscription->kind = SNAPSHOT_ACTIVE;
    subscription->owner = conversations;
    atomic_init(&subscription->destroy_attempts, 0);
    *out_subscription = subscription;
    callback(context, subscription, 0, new_snapshot(SNAPSHOT_ACTIVE, conversations->active_id, conversations), 0, user_data);
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) {
        if (atomic_load_explicit(&conversation_test_terminal, memory_order_acquire)) {
            callback(context, subscription, 0, new_snapshot(SNAPSHOT_ACTIVE, 0, conversations), 0, user_data);
            callback(context, subscription, 0, NULL, 1, user_data);
        } else {
            atomic_store_explicit(&conversation_subscription, subscription, memory_order_release);
        }
    }
    return 0;
}

static int string_equals(const string_view_t *value, const char *expected);

API status_t codex_agent_conversations_open(context_t *context, conversations_t *conversations, const conversation_open_options_t *options, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (conversations == NULL || conversations->context != context || options == NULL || options->struct_size != sizeof(conversation_open_options_t)) return 1;
    atomic_store_explicit(&last_open_has_conversation_id, options->has_conversation_id, memory_order_release);
    atomic_store_explicit(&last_open_conversation_id_size, (int32_t)options->conversation_id.size, memory_order_release);
    atomic_store_explicit(&last_open_has_service_tier, options->has_service_tier, memory_order_release);
    atomic_store_explicit(&last_open_service_tier_size, (int32_t)options->service_tier.size, memory_order_release);
    if (options->has_conversation_id && options->conversation_id.size == 0) return 1;
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) {
        if (options->has_conversation_id &&
            (!string_equals(&options->conversation_id, "conversation-open") ||
             !options->has_approval_preset || options->approval_preset != 2 ||
             !options->has_service_tier || !string_equals(&options->service_tier, "fast"))) return 1;
    }
    conversations->active_id = atomic_fetch_add_explicit(&next_conversation_id, 1, memory_order_acq_rel) + 1;
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) {
        status_t status = start_threaded_operation(context, callback, user_data, out_operation);
        if (status == 0) (*out_operation)->conversation_id = conversations->active_id;
        return status;
    }
    return start_operation(context, 0, conversations->active_id, 1, callback, user_data, out_operation);
}

API status_t codex_agent_conversation_release(context_t *context, conversation_t **conversation) {
    if (conversation == NULL || *conversation == NULL) return 0;
    if ((*conversation)->context != context) return 5;
    if (atomic_load_explicit(&owned_release_mode, memory_order_acquire) == 0 &&
        (*conversation)->state != 8 &&
        (*conversation)->id != atomic_load_explicit(&closed_conversation_id, memory_order_acquire)) return 6;
    status_t status = cleanup_status(&(*conversation)->release_attempts, &owned_release_mode);
    if (status != 0) return status;
    free(*conversation);
    *conversation = NULL;
    log_release('C');
    return 0;
}

API status_t codex_agent_conversation_is_same(context_t *context, conversation_t *left, conversation_t *right, int32_t *out_same) {
    if (left == NULL || right == NULL || out_same == NULL) return 1;
    if (left->context != context || right->context != context) return 5;
    *out_same = left->id == right->id;
    return 0;
}

static int string_equals(const string_view_t *value, const char *expected) {
    size_t size = strlen(expected);
    return value != NULL && value->size == size && (size == 0 || memcmp(value->data, expected, size) == 0);
}

API status_t codex_agent_conversation_send(context_t *context, conversation_t *conversation, const string_view_t *prompt, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (conversation == NULL || conversation->context != context || prompt == NULL) return 1;
    if (string_equals(prompt, "fail")) return start_operation(context, 14, 0, 1, callback, user_data, out_operation);
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire) && !string_equals(prompt, "h\xC3\xA9llo")) return 1;
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) return start_threaded_operation(context, callback, user_data, out_operation);
    if (string_equals(prompt, "pending")) return start_operation(context, 0, 0, 0, callback, user_data, out_operation);
    if (string_equals(prompt, "threaded")) return start_threaded_operation(context, callback, user_data, out_operation);
    return start_operation(context, 0, 0, 1, callback, user_data, out_operation);
}

API status_t codex_agent_conversation_run_shell_command(context_t *context, conversation_t *conversation, const string_view_t *command, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (command == NULL) return 1;
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire) &&
        !string_equals(command, "pwd") && !string_equals(command, "sleep")) return 1;
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire) && string_equals(command, "pwd"))
        return start_threaded_operation(context, callback, user_data, out_operation);
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire) && string_equals(command, "sleep"))
        return start_operation(context, 0, 0, 0, callback, user_data, out_operation);
    return codex_agent_conversation_send(context, conversation, command, callback, user_data, out_operation);
}

#define CONVERSATION_OPERATION(name) \
API status_t name(context_t *context, conversation_t *conversation, operation_callback_t callback, void *user_data, operation_t **out_operation) { \
    if (conversation == NULL || conversation->context != context) return 5; \
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) return start_threaded_operation(context, callback, user_data, out_operation); \
    return start_operation(context, 0, 0, 1, callback, user_data, out_operation); \
}

CONVERSATION_OPERATION(codex_agent_conversation_reload)
CONVERSATION_OPERATION(codex_agent_conversation_cancel_turn)

API status_t codex_agent_conversation_close(context_t *context, conversation_t *conversation, operation_callback_t callback, void *user_data, operation_t **out_operation) {
    if (conversation == NULL || conversation->context != context) return 5;
    conversation->state = 8;
    atomic_store_explicit(&closed_conversation_id, conversation->id, memory_order_release);
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) return start_threaded_operation(context, callback, user_data, out_operation);
    return start_operation(context, 0, 0, 1, callback, user_data, out_operation);
}

API status_t codex_agent_conversation_state_get(context_t *context, conversation_t *conversation, snapshot_t **out_snapshot) {
    if (conversation == NULL || conversation->context != context || out_snapshot == NULL || *out_snapshot != NULL) return 1;
    *out_snapshot = new_snapshot(SNAPSHOT_CONVERSATION, conversation->state, conversation);
    return 0;
}

API status_t codex_agent_conversation_state_subscribe(context_t *context, conversation_t *conversation, state_callback_t callback, void *user_data, subscription_t **out_subscription) {
    if (conversation == NULL || conversation->context != context || callback == NULL || out_subscription == NULL || *out_subscription != NULL) return 1;
    subscription_t *subscription = (subscription_t *)calloc(1, sizeof(subscription_t));
    subscription->context = context;
    subscription->callback = callback;
    subscription->user_data = user_data;
    subscription->kind = SNAPSHOT_CONVERSATION;
    subscription->owner = conversation;
    atomic_init(&subscription->destroy_attempts, 0);
    *out_subscription = subscription;
    callback(context, subscription, 0, new_snapshot(SNAPSHOT_CONVERSATION, conversation->state, conversation), 0, user_data);
    if (atomic_load_explicit(&conversation_test_mode, memory_order_acquire)) {
        if (atomic_load_explicit(&conversation_test_terminal, memory_order_acquire)) {
            callback(context, subscription, 0, new_snapshot(SNAPSHOT_CONVERSATION, 5, conversation), 0, user_data);
            callback(context, subscription, 0, NULL, 1, user_data);
        } else {
            atomic_store_explicit(&conversation_subscription, subscription, memory_order_release);
        }
    }
    return 0;
}

API status_t codex_agent_operation_cancel(context_t *context, operation_t *operation) {
    if (operation == NULL || operation->context != context) return 5;
    atomic_store_explicit(&operation->result, 7, memory_order_release);
    atomic_store_explicit(&operation->complete, 1, memory_order_release);
    if (atomic_exchange_explicit(&operation->callback_sent, 1, memory_order_acq_rel) == 0) {
        atomic_store_explicit(&operation->callback_active, 1, memory_order_release);
        operation->callback(context, operation, operation->user_data);
        atomic_store_explicit(&operation->callback_active, 0, memory_order_release);
    }
    return 0;
}

API status_t codex_agent_operation_result(context_t *context, operation_t *operation, status_t *out_result) {
    if (operation == NULL || operation->context != context || out_result == NULL) return 1;
    if (!atomic_load_explicit(&operation->complete, memory_order_acquire)) return 13;
    *out_result = atomic_load_explicit(&operation->result, memory_order_acquire);
    return 0;
}

API status_t codex_agent_operation_conversation(context_t *context, conversations_t *conversations, operation_t *operation, conversation_t **out_conversation) {
    if (conversations == NULL || operation == NULL || out_conversation == NULL || *out_conversation != NULL) return 1;
    if (conversations->context != context || operation->context != context) return 5;
    conversation_t *conversation = (conversation_t *)calloc(1, sizeof(conversation_t));
    conversation->context = context;
    conversation->id = operation->conversation_id;
    conversation->state = 2;
    atomic_init(&conversation->release_attempts, 0);
    *out_conversation = conversation;
    return 0;
}

API status_t codex_agent_operation_failure(context_t *context, operation_t *operation, failure_t **out_failure) {
    if (operation == NULL || operation->context != context || out_failure == NULL || *out_failure != NULL) return 1;
    if (atomic_load_explicit(&operation->result, memory_order_acquire) != 14) return 13;
    failure_t *failure = (failure_t *)calloc(1, sizeof(failure_t));
    failure->code = strdup("mock.failure");
    failure->message = strdup("structured failure");
    failure->recoverable = 1;
    atomic_init(&failure->release_attempts, 0);
    *out_failure = failure;
    return 0;
}

API status_t codex_agent_operation_destroy(context_t *context, operation_t **operation) {
    if (operation == NULL || *operation == NULL) return 0;
    if ((*operation)->context != context) return 5;
    if (!atomic_load_explicit(&(*operation)->complete, memory_order_acquire) ||
        atomic_load_explicit(&(*operation)->callback_active, memory_order_acquire) ||
        !atomic_load_explicit(&(*operation)->worker_done, memory_order_acquire)) return 6;
    status_t status = cleanup_status(&(*operation)->destroy_attempts, &operation_destroy_mode);
    if (status != 0) return status;
    free(*operation);
    *operation = NULL;
    atomic_fetch_add_explicit(&operation_destroy_count, 1, memory_order_acq_rel);
    return 0;
}

API status_t codex_agent_subscription_destroy(context_t *context, subscription_t **subscription) {
    if (subscription == NULL || *subscription == NULL) return 0;
    if ((*subscription)->context != context) return 5;
    status_t status = cleanup_status(&(*subscription)->destroy_attempts, &subscription_destroy_mode);
    if (status != 0) return status;
    pthread_mutex_lock(&host_subscription_mutex);
    subscription_t *published = atomic_load_explicit(&host_subscription, memory_order_acquire);
    if (published == *subscription) atomic_store_explicit(&host_subscription, NULL, memory_order_release);
    published = atomic_load_explicit(&conversation_subscription, memory_order_acquire);
    if (published == *subscription) atomic_store_explicit(&conversation_subscription, NULL, memory_order_release);
    free(*subscription);
    pthread_mutex_unlock(&host_subscription_mutex);
    *subscription = NULL;
    atomic_fetch_add_explicit(&subscription_destroy_count, 1, memory_order_acq_rel);
    return 0;
}

API status_t codex_agent_snapshot_destroy(context_t *context, snapshot_t **snapshot) {
    (void)context;
    if (snapshot == NULL || *snapshot == NULL) return 0;
    free(*snapshot);
    *snapshot = NULL;
    return 0;
}

API status_t codex_agent_host_state_kind(context_t *context, snapshot_t *snapshot, int32_t *out_kind) {
    (void)context;
    if (snapshot == NULL || snapshot->kind != SNAPSHOT_HOST || out_kind == NULL) return 1;
    *out_kind = snapshot->value;
    return 0;
}

API status_t codex_agent_host_state_agent(context_t *context, host_t *host, snapshot_t *snapshot, agent_t **out_agent) {
    if (host == NULL || host->context != context || snapshot == NULL || snapshot->value != 4 || out_agent == NULL || *out_agent != NULL) return 13;
    agent_t *agent = (agent_t *)calloc(1, sizeof(agent_t));
    agent->context = context;
    agent->host = host;
    atomic_init(&agent->release_attempts, 0);
    *out_agent = agent;
    return 0;
}

API status_t codex_agent_host_state_failure(context_t *context, snapshot_t *snapshot, failure_t **out_failure) {
    (void)context; (void)snapshot; (void)out_failure;
    return 13;
}

API status_t codex_agent_host_state_has_workspace(context_t *context, snapshot_t *snapshot, int32_t *out_has_workspace) {
    (void)context;
    if (snapshot == NULL || out_has_workspace == NULL) return 1;
    *out_has_workspace = snapshot->value == 4 &&
        atomic_load_explicit(&host_workspace_available, memory_order_acquire);
    return 0;
}

API status_t codex_agent_host_state_workspace_path_copy(context_t *context, snapshot_t *snapshot, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; (void)snapshot;
    if (!atomic_load_explicit(&host_workspace_available, memory_order_acquire)) return 13;
    return copy_text("/tmp/workspace", buffer, capacity, out_required);
}

API status_t codex_agent_host_state_workspace_display_name_copy(context_t *context, snapshot_t *snapshot, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; (void)snapshot;
    if (!atomic_load_explicit(&host_workspace_available, memory_order_acquire)) return 13;
    return copy_text("Workspace", buffer, capacity, out_required);
}

API status_t codex_agent_host_state_requirement_reason(context_t *context, snapshot_t *snapshot, int32_t *out_reason) {
    (void)context; (void)snapshot;
    if (out_reason == NULL) return 1;
    *out_reason = 0;
    return 0;
}

API status_t codex_agent_host_state_requirement_message_copy(context_t *context, snapshot_t *snapshot, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; (void)snapshot;
    return copy_text("Select a workspace", buffer, capacity, out_required);
}

API status_t codex_agent_active_conversation(context_t *context, conversations_t *conversations, snapshot_t *snapshot, conversation_t **out_conversation) {
    if (conversations == NULL || conversations->context != context || snapshot == NULL || out_conversation == NULL || *out_conversation != NULL) return 1;
    if (snapshot->value == 0) return 0;
    conversation_t *conversation = (conversation_t *)calloc(1, sizeof(conversation_t));
    conversation->context = context;
    conversation->id = snapshot->value;
    conversation->state = 2;
    atomic_init(&conversation->release_attempts, 0);
    *out_conversation = conversation;
    return 0;
}

API status_t codex_agent_conversation_state_status(context_t *context, snapshot_t *snapshot, int32_t *out_status) {
    (void)context;
    if (snapshot == NULL || snapshot->kind != SNAPSHOT_CONVERSATION || out_status == NULL) return 1;
    *out_status = snapshot->value;
    return 0;
}

API status_t codex_agent_conversation_state_failure(context_t *context, snapshot_t *snapshot, failure_t **out_failure) {
    (void)context; (void)snapshot; (void)out_failure;
    return 13;
}

API status_t codex_agent_failure_release(context_t *context, failure_t **failure) {
    (void)context;
    if (failure == NULL || *failure == NULL) return 0;
    status_t status = cleanup_status(&(*failure)->release_attempts, &failure_release_mode);
    if (status != 0) return status;
    free((*failure)->code);
    free((*failure)->message);
    free(*failure);
    *failure = NULL;
    return 0;
}

API status_t codex_agent_failure_code_copy(context_t *context, failure_t *failure, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    if (failure == NULL) return 1;
    return copy_text(failure->code, buffer, capacity, out_required);
}

API status_t codex_agent_failure_message_copy(context_t *context, failure_t *failure, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    if (failure == NULL) return 1;
    return copy_text(failure->message, buffer, capacity, out_required);
}

API status_t codex_agent_failure_is_recoverable(context_t *context, failure_t *failure, int32_t *out_recoverable) {
    (void)context;
    if (failure == NULL || out_recoverable == NULL) return 1;
    *out_recoverable = failure->recoverable;
    return 0;
}

API void codex_agent_test_publish_host_state(void) {
    pthread_mutex_lock(&host_subscription_mutex);
    subscription_t *subscription = atomic_load_explicit(&host_subscription, memory_order_acquire);
    if (subscription == NULL) {
        pthread_mutex_unlock(&host_subscription_mutex);
        return;
    }
    host_t *host = (host_t *)subscription->owner;
    subscription->callback(
        subscription->context,
        subscription,
        0,
        new_snapshot(SNAPSHOT_HOST, host->state, host),
        0,
        subscription->user_data);
    pthread_mutex_unlock(&host_subscription_mutex);
}

API status_t codex_agent_test_publish_host_state_status(void) {
    pthread_mutex_lock(&host_subscription_mutex);
    subscription_t *subscription = atomic_load_explicit(&host_subscription, memory_order_acquire);
    if (subscription == NULL) {
        pthread_mutex_unlock(&host_subscription_mutex);
        return 13;
    }
    host_t *host = (host_t *)subscription->owner;
    subscription->callback(
        subscription->context,
        subscription,
        0,
        new_snapshot(SNAPSHOT_HOST, host->state, host),
        0,
        subscription->user_data);
    pthread_mutex_unlock(&host_subscription_mutex);
    return 0;
}

API status_t codex_agent_test_set_host_state(context_t *context, host_t *host, int32_t state) {
    if (host == NULL || host->context != context || state < 0 || state > 6) return 1;
    host->state = state;
    return 0;
}

API void codex_agent_test_finish_host_state(void) {
    pthread_mutex_lock(&host_subscription_mutex);
    subscription_t *subscription = atomic_load_explicit(&host_subscription, memory_order_acquire);
    if (subscription == NULL) {
        pthread_mutex_unlock(&host_subscription_mutex);
        return;
    }
    subscription->callback(
        subscription->context,
        subscription,
        0,
        NULL,
        1,
        subscription->user_data);
    pthread_mutex_unlock(&host_subscription_mutex);
}

API int32_t codex_agent_test_context_destroy_errors(void) {
    return atomic_load_explicit(&context_destroy_errors, memory_order_acquire);
}
API int32_t codex_agent_test_operation_destroy_count(void) {
    return atomic_load_explicit(&operation_destroy_count, memory_order_acquire);
}
API int32_t codex_agent_test_subscription_destroy_count(void) {
    return atomic_load_explicit(&subscription_destroy_count, memory_order_acquire);
}
API int32_t codex_agent_test_agent_children_live(void) {
    return atomic_load_explicit(&agent_children_live, memory_order_acquire);
}
API int32_t codex_agent_test_agent_release_with_live_children_errors(void) {
    return atomic_load_explicit(&agent_release_with_live_children_errors, memory_order_acquire);
}
API status_t codex_agent_test_release_log_copy(uint8_t *buffer, size_t capacity, size_t *out_required) {
    if (out_required == NULL) return 1;
    pthread_mutex_lock(&release_log_mutex);
    *out_required = release_log_size;
    if (capacity < release_log_size) {
        pthread_mutex_unlock(&release_log_mutex);
        return 9;
    }
    if (release_log_size != 0 && buffer == NULL) {
        pthread_mutex_unlock(&release_log_mutex);
        return 1;
    }
    if (release_log_size != 0) memcpy(buffer, release_log, release_log_size);
    pthread_mutex_unlock(&release_log_mutex);
    return 0;
}
API void codex_agent_test_set_abi_compatible(int32_t value) {
    atomic_store_explicit(&abi_compatible, value, memory_order_release);
}
API void codex_agent_test_set_identity_mode(int32_t value) {
    atomic_store_explicit(&identity_mode, value, memory_order_release);
}
API void codex_agent_test_set_operation_destroy_mode(int32_t value) {
    atomic_store_explicit(&operation_destroy_mode, value, memory_order_release);
}
API void codex_agent_test_set_subscription_destroy_mode(int32_t value) {
    atomic_store_explicit(&subscription_destroy_mode, value, memory_order_release);
}
API void codex_agent_test_set_owned_release_mode(int32_t value) {
    atomic_store_explicit(&owned_release_mode, value, memory_order_release);
}
API void codex_agent_test_set_failure_release_mode(int32_t value) {
    atomic_store_explicit(&failure_release_mode, value, memory_order_release);
}
API void codex_agent_test_set_context_destroy_mode(int32_t value) {
    atomic_store_explicit(&context_destroy_mode, value, memory_order_release);
}
API void codex_agent_test_set_host_workspace_available(int32_t value) {
    atomic_store_explicit(&host_workspace_available, value, memory_order_release);
}
API void codex_agent_test_set_host_operation_result(int32_t value) {
    atomic_store_explicit(&host_operation_result, value, memory_order_release);
}
API void codex_agent_test_set_host_operation_completion_mode(int32_t value) {
    atomic_store_explicit(&host_operation_completion_mode, value, memory_order_release);
}
API void codex_agent_test_require_exact_host_inputs(int32_t value) {
    atomic_store_explicit(&require_exact_host_inputs, value, memory_order_release);
}
API int32_t codex_agent_test_copied_host_option_equals(int32_t index, const string_view_t *expected) {
    if (index < 0 || index >= 5 || expected == NULL) return 0;
    return host_view_equals(expected, copied_host_options[index]);
}
API int32_t codex_agent_test_copied_workspace_selection_equals(const string_view_t *expected) {
    if (expected == NULL) return 0;
    return host_view_equals(expected, copied_workspace_selection);
}
API int32_t codex_agent_test_last_open_has_conversation_id(void) {
    return atomic_load_explicit(&last_open_has_conversation_id, memory_order_acquire);
}
API int32_t codex_agent_test_last_open_conversation_id_size(void) {
    return atomic_load_explicit(&last_open_conversation_id_size, memory_order_acquire);
}
API int32_t codex_agent_test_last_open_has_service_tier(void) {
    return atomic_load_explicit(&last_open_has_service_tier, memory_order_acquire);
}
API int32_t codex_agent_test_last_open_service_tier_size(void) {
    return atomic_load_explicit(&last_open_service_tier_size, memory_order_acquire);
}
