#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#include <stdatomic.h>
#endif

#if defined(_WIN32)
#define API __declspec(dllexport)
#define CALL __cdecl
#else
#define API __attribute__((visibility("default")))
#define CALL
#endif

enum { OK = 0, BUSY = 6, CANCELLED = 7, BUFFER_TOO_SMALL = 9, NOT_READY = 13, OPERATION_FAILED = 14 };

#if defined(_WIN32)
typedef volatile LONG test_atomic_int_t;
static int test_load(test_atomic_int_t *value) { return (int)InterlockedCompareExchange(value, 0, 0); }
static void test_store(test_atomic_int_t *value, int next) { InterlockedExchange(value, (LONG)next); }
static void test_increment(test_atomic_int_t *value) { InterlockedIncrement(value); }
static void test_decrement(test_atomic_int_t *value) { InterlockedDecrement(value); }
#else
typedef _Atomic int test_atomic_int_t;
static int test_load(test_atomic_int_t *value) { return atomic_load(value); }
static void test_store(test_atomic_int_t *value, int next) { atomic_store(value, next); }
static void test_increment(test_atomic_int_t *value) { (void)atomic_fetch_add(value, 1); }
static void test_decrement(test_atomic_int_t *value) { (void)atomic_fetch_sub(value, 1); }
#endif

typedef struct handle {
  int kind;
  int result;
  char text[128];
  char second[128];
  int busy_remaining;
  test_atomic_int_t cancel_requested;
  test_atomic_int_t worker_complete;
  int has_worker;
#if defined(_WIN32)
  HANDLE worker;
#else
  pthread_t worker;
#endif
} handle_t;

static test_atomic_int_t active_operations = 0;
static test_atomic_int_t active_subscriptions = 0;
static test_atomic_int_t emit_terminal_state = 1;
static test_atomic_int_t fail_next_operation = 0;
static test_atomic_int_t fail_operation_destroy_once = 0;
static test_atomic_int_t fail_host_release_once = 0;
static test_atomic_int_t host_close_calls = 0;
static test_atomic_int_t host_release_calls = 0;
static test_atomic_int_t context_destroy_calls = 0;
static test_atomic_int_t agent_released = 0;
static test_atomic_int_t agent_release_calls = 0;
static test_atomic_int_t host_parity_mode = 0;

typedef struct leaf_call_entry {
  const char *symbol;
  test_atomic_int_t count;
} leaf_call_entry_t;

static leaf_call_entry_t leaf_calls[128];
static test_atomic_int_t leaf_call_size = 0;

static void leaf_record(const char *symbol) {
  int count = test_load(&leaf_call_size);
  int index;
  for (index = 0; index < count; index++) {
    if (strcmp(leaf_calls[index].symbol, symbol) == 0) {
      test_increment(&leaf_calls[index].count);
      return;
    }
  }
  if (count < 128) {
    leaf_calls[count].symbol = symbol;
    test_store(&leaf_calls[count].count, 1);
    test_store(&leaf_call_size, count + 1);
  }
}

API int CALL codex_agent_dart_leaf_call_count(const char *symbol) {
  int count = test_load(&leaf_call_size);
  int index;
  if (symbol == NULL) return 0;
  for (index = 0; index < count; index++) {
    if (strcmp(leaf_calls[index].symbol, symbol) == 0) {
      return test_load(&leaf_calls[index].count);
    }
  }
  return 0;
}

typedef struct string_view {
  const uint8_t *data;
  size_t size;
} string_view_t;

typedef struct client_info {
  uint32_t struct_size;
  string_view_t name;
  string_view_t title;
  string_view_t version;
} client_info_t;

typedef struct host_options {
  uint32_t struct_size;
  string_view_t bundle_directory;
  string_view_t data_directory;
  client_info_t client_info;
} host_options_t;

typedef struct path_selection {
  uint32_t struct_size;
  string_view_t path;
} path_selection_t;

typedef struct open_options {
  uint32_t struct_size;
  int32_t has_conversation_id;
  string_view_t conversation_id;
  int32_t has_approval_preset;
  int32_t approval_preset;
  int32_t has_service_tier;
  string_view_t service_tier;
} open_options_t;

typedef void (CALL *operation_callback_t)(void *, void *, void *);
typedef void (CALL *state_callback_t)(void *, void *, int32_t, void *, int32_t, void *);

static handle_t *new_handle(int kind) {
  handle_t *value = (handle_t *)calloc(1, sizeof(handle_t));
  if (value != NULL) {
    value->kind = kind;
    value->busy_remaining = 1;
  }
  return value;
}

static int release_handle(void **slot) {
  if (slot == NULL) return 1;
  if (*slot != NULL && ((handle_t *)*slot)->busy_remaining > 0) {
    ((handle_t *)*slot)->busy_remaining--;
    return BUSY;
  }
  free(*slot);
  *slot = NULL;
  return OK;
}

static int copy_bytes(const char *value, uint8_t *buffer, size_t capacity, size_t *required) {
  size_t length = strlen(value);
  if (required == NULL) return 1;
  *required = length;
  if (capacity < length) return BUFFER_TOO_SMALL;
  if (length != 0 && buffer != NULL) memcpy(buffer, value, length);
  return OK;
}

static int view_equals(const string_view_t *view, const char *expected) {
  size_t length = strlen(expected);
  return view != NULL && view->size == length &&
      (length == 0 || memcmp(view->data, expected, length) == 0);
}

static int copy_view(char *target, size_t capacity, const string_view_t *view) {
  if (target == NULL || view == NULL || view->size >= capacity) return 1;
  if (view->size != 0) memcpy(target, view->data, view->size);
  target[view->size] = '\0';
  return OK;
}

static int destroy_value(void **slot) {
  if (slot == NULL) return 1;
  free(*slot);
  *slot = NULL;
  return OK;
}

static int value_out(void **out, int kind);
static int value_release(void **slot);

typedef struct operation_args {
  void *context;
  handle_t *operation;
  operation_callback_t callback;
  void *user_data;
} operation_args_t;

static void callback_delay(void) {
#if defined(_WIN32)
  Sleep(5);
#else
  struct timespec delay = {0, 5000000};
  nanosleep(&delay, NULL);
#endif
}

static void run_operation_callback(operation_args_t *args) {
  callback_delay();
  args->callback(args->context, args->operation, args->user_data);
  free(args);
}

#if defined(_WIN32)
static DWORD WINAPI operation_worker(LPVOID value) {
  run_operation_callback((operation_args_t *)value);
  return 0;
}
#else
static void *operation_worker(void *value) {
  run_operation_callback((operation_args_t *)value);
  return NULL;
}
#endif

static int operation(void *context, operation_callback_t callback, void *user_data, void **out, int kind) {
  (void)context;
  if (out == NULL || *out != NULL || callback == NULL) return 1;
  handle_t *value = new_handle(kind);
  if (value == NULL) return 2;
  int forced_failure = test_load(&fail_next_operation);
  if (forced_failure != 0) test_store(&fail_next_operation, 0);
  value->result = kind == 99 || forced_failure != 0 ? OPERATION_FAILED : OK;
  *out = value;
  operation_args_t *args = (operation_args_t *)calloc(1, sizeof(operation_args_t));
  if (args == NULL) { free(value); *out = NULL; return 2; }
  args->context = context;
  args->operation = value;
  args->callback = callback;
  args->user_data = user_data;
#if defined(_WIN32)
  HANDLE thread = CreateThread(NULL, 0, operation_worker, args, 0, NULL);
  if (thread == NULL) { free(args); free(value); *out = NULL; return 8; }
  CloseHandle(thread);
#else
  pthread_t thread;
  if (pthread_create(&thread, NULL, operation_worker, args) != 0) {
    free(args); free(value); *out = NULL; return 8;
  }
  pthread_detach(thread);
#endif
  test_increment(&active_operations);
  return OK;
}

static int snapshot_get(void **out, int kind) {
  if (out == NULL || *out != NULL) return 1;
  *out = new_handle(kind);
  return *out == NULL ? 2 : OK;
}

typedef struct state_args {
  void *context;
  handle_t *subscription;
  state_callback_t callback;
  void *user_data;
  int kind;
  int initial_result;
  int emit_terminal;
} state_args_t;

static void run_state_callbacks(state_args_t *args) {
  callback_delay();
  if (test_load(&args->subscription->cancel_requested) == 0) {
    handle_t *changed = new_handle(args->kind);
    if (changed != NULL) changed->result = args->initial_result;
    args->callback(args->context, args->subscription, OK, changed, 0, args->user_data);
  }
  if (args->kind == 61) {
    int result;
    for (result = 3; result <= 4; result++) {
      if (test_load(&args->subscription->cancel_requested) != 0) break;
      handle_t *changed = new_handle(args->kind);
      if (changed != NULL) changed->result = result;
      args->callback(args->context, args->subscription, OK, changed, 0, args->user_data);
    }
  }
  if (args->emit_terminal != 0 && test_load(&args->subscription->cancel_requested) == 0) {
    handle_t *terminal = new_handle(args->kind);
    if (terminal != NULL) terminal->result = 2;
    args->callback(args->context, args->subscription, OK, terminal, 1, args->user_data);
  }
  test_store(&args->subscription->worker_complete, 1);
  free(args);
}

#if defined(_WIN32)
static DWORD WINAPI state_worker(LPVOID value) {
  run_state_callbacks((state_args_t *)value);
  return 0;
}
#else
static void *state_worker(void *value) {
  run_state_callbacks((state_args_t *)value);
  return NULL;
}
#endif

static int subscribe_with_initial(
    void *context,
    state_callback_t callback,
    void *user_data,
    void **out,
    int kind,
    int initial_result) {
  if (out == NULL || *out != NULL || callback == NULL) return 1;
  *out = new_handle(40);
  if (*out == NULL) return 2;
  state_args_t *args = (state_args_t *)calloc(1, sizeof(state_args_t));
  if (args == NULL) { free(*out); *out = NULL; return 2; }
  args->context = context;
  args->subscription = (handle_t *)*out;
  args->callback = callback;
  args->user_data = user_data;
  args->kind = kind;
  args->initial_result = initial_result;
  args->emit_terminal = test_load(&emit_terminal_state);
  handle_t *subscription = (handle_t *)*out;
#if defined(_WIN32)
  HANDLE thread = CreateThread(NULL, 0, state_worker, args, 0, NULL);
  if (thread == NULL) { free(args); free(subscription); *out = NULL; return 8; }
  subscription->worker = thread;
#else
  if (pthread_create(&subscription->worker, NULL, state_worker, args) != 0) {
    free(args); free(subscription); *out = NULL; return 8;
  }
#endif
  subscription->has_worker = 1;
  test_increment(&active_subscriptions);
  return OK;
}

static int subscribe(void *context, state_callback_t callback, void *user_data, void **out, int kind) {
  return subscribe_with_initial(context, callback, user_data, out, kind, 1);
}

API uint32_t CALL codex_agent_abi_version(void) { return (1u << 24) | (12u << 16); }
API int32_t CALL codex_agent_abi_is_compatible(uint32_t requested) {
  return (requested >> 24) == 1u;
}
API void CALL codex_agent_test_emit_terminal_state(int32_t enabled) {
  test_store(&emit_terminal_state, enabled);
}
API void CALL codex_agent_dart_test_fail_next_operation(void) {
  test_store(&fail_next_operation, 1);
}
API void CALL codex_agent_test_fail_operation_destroy_once(void) {
  test_store(&fail_operation_destroy_once, 1);
}
API void CALL codex_agent_test_fail_host_release_once(void) {
  test_store(&fail_host_release_once, 1);
}
API void CALL codex_agent_dart_test_host_parity_mode(int32_t enabled) {
  test_store(&host_parity_mode, enabled);
}
API int32_t CALL codex_agent_dart_test_agent_release_calls(void) {
  return test_load(&agent_release_calls);
}

API int CALL codex_agent_context_create(void **out) { return snapshot_get(out, 1); }
API int CALL codex_agent_context_destroy(void **slot) {
  int status = release_handle(slot);
  if (status == OK) test_increment(&context_destroy_calls);
  return status;
}
API int32_t CALL codex_agent_test_host_close_calls(void) { return test_load(&host_close_calls); }
API int32_t CALL codex_agent_test_host_release_calls(void) { return test_load(&host_release_calls); }
API int32_t CALL codex_agent_test_context_destroy_calls(void) { return test_load(&context_destroy_calls); }

API int CALL codex_agent_host_create(void *context, const host_options_t *options, void **out) {
  (void)context;
  leaf_record("codex_agent_host_create");
  if (options == NULL || options->struct_size != sizeof(host_options_t)) return 1;
  if (test_load(&host_parity_mode) != 0 &&
      (!view_equals(&options->bundle_directory, "/host-parity-bundle") ||
       !view_equals(&options->data_directory, "/host-parity-data") ||
       options->client_info.struct_size != sizeof(client_info_t) ||
       !view_equals(&options->client_info.name, "host-parity") ||
       !view_equals(&options->client_info.title, "Host parity") ||
       !view_equals(&options->client_info.version, "1.0"))) return 1;
  return snapshot_get(out, 2);
}
API int CALL codex_agent_host_release(void *context, void **slot) {
  (void)context;
  if (test_load(&active_operations) != 0 || test_load(&active_subscriptions) != 0) return BUSY;
  if (test_load(&fail_host_release_once) != 0) {
    test_store(&fail_host_release_once, 0);
    return 8;
  }
  int status = release_handle(slot);
  if (status == OK) test_increment(&host_release_calls);
  return status;
}
API int CALL codex_agent_host_start(void *c, void *h, operation_callback_t cb, void *u, void **out) {
  (void)h; leaf_record("codex_agent_host_start"); return operation(c, cb, u, out, 10);
}
API int CALL codex_agent_host_select_workspace(void *c, void *h, const path_selection_t *s, operation_callback_t cb, void *u, void **out) {
  (void)h; leaf_record("codex_agent_host_select_workspace");
  if (s == NULL || s->struct_size != sizeof(path_selection_t)) return 1;
  if (test_load(&host_parity_mode) != 0 &&
      !view_equals(&s->path, "/selected-workspace")) return 1;
  return operation(c, cb, u, out, 10);
}
API int CALL codex_agent_host_close(void *c, void *h, operation_callback_t cb, void *u, void **out) {
  (void)h; leaf_record("codex_agent_host_close");
  test_increment(&host_close_calls); return operation(c, cb, u, out, 10);
}
API int CALL codex_agent_host_state_get(void *c, void *h, void **out) {
  (void)c; (void)h; leaf_record("codex_agent_host_state_get"); return snapshot_get(out, 4);
}
API int CALL codex_agent_host_state_subscribe(void *c, void *h, state_callback_t cb, void *u, void **out) {
  (void)h; leaf_record("codex_agent_host_state_subscribe"); return subscribe(c, cb, u, out, 4);
}

API int CALL codex_agent_agent_release(void *c, void **slot) {
  (void)c;
  leaf_record("codex_agent_agent_release");
  int status = release_handle(slot);
  if (status == OK) {
    test_store(&agent_released, 1);
    test_increment(&agent_release_calls);
  }
  return status;
}
API int CALL codex_agent_agent_conversations(void *c, void *a, void **out) {
  (void)c; (void)a; leaf_record("codex_agent_agent_conversations"); return snapshot_get(out, 3);
}
API int CALL codex_agent_agent_workspace(void *c, void *a, void **out) {
  (void)c; (void)a; leaf_record("codex_agent_agent_workspace"); return value_out(out, 70);
}
API int CALL codex_agent_workspace_destroy(void *c, void **slot) {
  (void)c; leaf_record("codex_agent_workspace_destroy"); return value_release(slot);
}
API int CALL codex_agent_workspace_path_copy(void *c, void *workspace, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)workspace; leaf_record("codex_agent_workspace_path_copy"); return copy_bytes("/agent-workspace", b, n, r);
}
API int CALL codex_agent_workspace_display_name_copy(void *c, void *workspace, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)workspace; leaf_record("codex_agent_workspace_display_name_copy"); return copy_bytes("Agent Workspace", b, n, r);
}
API int CALL codex_agent_conversations_release(void *c, void **slot) {
  (void)c; leaf_record("codex_agent_conversations_release"); return release_handle(slot);
}
API int CALL codex_agent_conversations_active_get(void *c, void *v, void **out) {
  (void)c; (void)v; leaf_record("codex_agent_conversations_active_get");
  if (test_load(&agent_released) != 0) return 1;
  return snapshot_get(out, 5);
}
API int CALL codex_agent_conversations_active_subscribe(void *c, void *v, state_callback_t cb, void *u, void **out) {
  (void)v; leaf_record("codex_agent_conversations_active_subscribe"); return subscribe(c, cb, u, out, 5);
}
API int CALL codex_agent_conversations_list(void *c, void *v, operation_callback_t cb, void *u, void **out) {
  (void)v; leaf_record("codex_agent_conversations_list"); return operation(c, cb, u, out, 11);
}
API int CALL codex_agent_conversations_read(void *c, void *v, void *id, operation_callback_t cb, void *u, void **out) {
  (void)v;
  leaf_record("codex_agent_conversations_read");
  if (id == NULL || strcmp(((handle_t *)id)->text, "conversation-1") != 0) return 1;
  return operation(c, cb, u, out, 13);
}
API int CALL codex_agent_conversations_rename(void *c, void *v, void *id, const string_view_t *name, operation_callback_t cb, void *u, void **out) {
  (void)v;
  leaf_record("codex_agent_conversations_rename");
  if (id == NULL || strcmp(((handle_t *)id)->text, "conversation-1") != 0 ||
      !view_equals(name, "renamed")) return 1;
  return operation(c, cb, u, out, 10);
}
API int CALL codex_agent_conversations_delete(void *c, void *v, void *id, operation_callback_t cb, void *u, void **out) {
  (void)v;
  leaf_record("codex_agent_conversations_delete");
  if (id == NULL || strcmp(((handle_t *)id)->text, "conversation-1") != 0) return 1;
  return operation(c, cb, u, out, 10);
}
API int CALL codex_agent_conversations_open(void *c, void *v, const open_options_t *o, operation_callback_t cb, void *u, void **out) {
  (void)v;
  leaf_record("codex_agent_conversations_open");
  if (o == NULL || o->struct_size != sizeof(open_options_t)) return 1;
  int defaults = o->has_conversation_id == 0 && o->has_approval_preset == 0 &&
      o->has_service_tier == 0;
  int exact = o->has_conversation_id == 1 &&
      view_equals(&o->conversation_id, "conversation-2") &&
      o->has_approval_preset == 1 && o->approval_preset == 2 &&
      o->has_service_tier == 1 && view_equals(&o->service_tier, "priority");
  int auto_review = o->has_conversation_id == 0 &&
      o->has_approval_preset == 1 && o->approval_preset == 1 &&
      o->has_service_tier == 1 && view_equals(&o->service_tier, "default");
  if (!defaults && !exact && !auto_review) return 1;
  return operation(c, cb, u, out, auto_review ? 112 : 12);
}

API int CALL codex_agent_conversation_release(void *c, void **slot) { (void)c; return release_handle(slot); }
API int CALL codex_agent_conversation_is_same(void *c, void *left, void *right, int32_t *same) {
  (void)c;
  if (left == NULL || right == NULL || same == NULL) return 1;
  *same = ((handle_t *)left)->kind == ((handle_t *)right)->kind &&
      strcmp(((handle_t *)left)->text, ((handle_t *)right)->text) == 0;
  return OK;
}
API int CALL codex_agent_conversation_send(void *c, void *v, const string_view_t *s, operation_callback_t cb, void *u, void **out) {
  (void)v;
  leaf_record("codex_agent_conversation_send");
  if (!view_equals(s, "hello") && !view_equals(s, "fail")) return 1;
  int kind = view_equals(s, "fail") ? 99 : 10;
  return operation(c, cb, u, out, kind);
}
API int CALL codex_agent_conversation_send_request(void *c, void *v, void *request, operation_callback_t cb, void *u, void **out) {
  (void)v;
  leaf_record("codex_agent_conversation_send_request");
  if (request == NULL || ((handle_t *)request)->kind != 82 ||
      ((handle_t *)request)->result != 1) return 1;
  return operation(c, cb, u, out, 10);
}
API int CALL codex_agent_conversation_run_shell_command(void *c, void *v, const string_view_t *s, operation_callback_t cb, void *u, void **out) {
  (void)v; leaf_record("codex_agent_conversation_run_shell_command"); if (!view_equals(s, "pwd")) return 1; return operation(c, cb, u, out, 10);
}
#define CONVERSATION_OPERATION(name) \
  API int CALL name(void *c, void *v, operation_callback_t cb, void *u, void **out) { \
    (void)v; leaf_record(#name); return operation(c, cb, u, out, 10); \
  }
CONVERSATION_OPERATION(codex_agent_conversation_reload)
CONVERSATION_OPERATION(codex_agent_conversation_cancel_turn)
CONVERSATION_OPERATION(codex_agent_conversation_close)
API int CALL codex_agent_conversation_state_get(void *c, void *v, void **out) {
  (void)c; (void)v; leaf_record("codex_agent_conversation_state_get"); return snapshot_get(out, 2);
}
API int CALL codex_agent_conversation_state_subscribe(void *c, void *v, state_callback_t cb, void *u, void **out) {
  handle_t *conversation = (handle_t *)v;
  leaf_record("codex_agent_conversation_state_subscribe");
  if (conversation == NULL) return 1;
  int initial_result = conversation->result == 0 ? 0 : 1;
  conversation->result++;
  return subscribe_with_initial(c, cb, u, out, 2, initial_result);
}

#define BOOL_STATE(name, current_ready) \
  API int CALL name##_get(void *c, void *v, void **out) { \
    (void)c; leaf_record(#name "_get"); \
    int status = snapshot_get(out, 1); \
    if (status == OK) { \
      int ready = current_ready && v != NULL && \
          strcmp(((handle_t *)v)->second, "current-ready") == 0; \
      ((handle_t *)*out)->result = ready ? 1 : 2; \
    } \
    return status; \
  } \
  API int CALL name##_subscribe(void *c, void *v, state_callback_t cb, void *u, void **out) { \
    (void)v; leaf_record(#name "_subscribe"); return subscribe(c, cb, u, out, 1); \
  }
BOOL_STATE(codex_agent_conversation_can_start_turn, 1)
BOOL_STATE(codex_agent_conversation_can_reload, 0)
BOOL_STATE(codex_agent_conversation_can_cancel_turn, 0)
BOOL_STATE(codex_agent_conversation_can_run_shell_command, 0)
BOOL_STATE(codex_agent_conversation_is_turn_active, 0)

API int CALL codex_agent_conversation_current_messages_get(void *c, void *v, void **out) {
  (void)c; (void)v; leaf_record("codex_agent_conversation_current_messages_get"); return snapshot_get(out, 60);
}
API int CALL codex_agent_conversation_current_messages_subscribe(void *c, void *v, state_callback_t cb, void *u, void **out) {
  (void)v; leaf_record("codex_agent_conversation_current_messages_subscribe"); return subscribe(c, cb, u, out, 60);
}
API int CALL codex_agent_conversation_active_turn_progress_get(void *c, void *v, void **out) {
  (void)c; (void)v; leaf_record("codex_agent_conversation_active_turn_progress_get"); return snapshot_get(out, 61);
}
API int CALL codex_agent_conversation_active_turn_progress_subscribe(void *c, void *v, state_callback_t cb, void *u, void **out) {
  (void)v; leaf_record("codex_agent_conversation_active_turn_progress_subscribe"); return subscribe(c, cb, u, out, 61);
}

API int CALL codex_agent_operation_cancel(void *c, void *operation_value) {
  (void)c; leaf_record("codex_agent_operation_cancel");
  ((handle_t *)operation_value)->result = CANCELLED; return OK;
}
API int CALL codex_agent_operation_result(void *c, void *operation_value, int32_t *result) {
  (void)c; leaf_record("codex_agent_operation_result"); if (result == NULL) return 1; *result = ((handle_t *)operation_value)->result; return OK;
}
API int CALL codex_agent_operation_conversation(void *c, void *v, void *o, void **out) {
  (void)c; (void)v;
  int status = snapshot_get(out, 20);
  if (status == OK && o != NULL && ((handle_t *)o)->kind == 112) {
    (void)strcpy(((handle_t *)*out)->second, "current-ready");
  }
  return status;
}
API int CALL codex_agent_operation_conversation_value(void *c, void *o, void **out) {
  (void)c;
  leaf_record("codex_agent_operation_conversation_value");
  if (o == NULL || ((handle_t *)o)->kind != 13) return 1;
  return snapshot_get(out, 62);
}
API int CALL codex_agent_operation_failure(void *c, void *o, void **out) {
  (void)c;
  if (((handle_t *)o)->result != OPERATION_FAILED) return NOT_READY;
  return snapshot_get(out, 50);
}
API int CALL codex_agent_operation_conversation_summaries_count(void *c, void *o, size_t *count) {
  (void)c; (void)o; leaf_record("codex_agent_operation_conversation_summaries_count"); if (count == NULL) return 1; *count = 2; return OK;
}
API int CALL codex_agent_operation_conversation_summary_at(void *c, void *o, size_t index, void **out) {
  (void)c; (void)o;
  leaf_record("codex_agent_operation_conversation_summary_at");
  if (index > 1) return 1;
  int status = snapshot_get(out, 30);
  if (status == OK) ((handle_t *)*out)->result = (int)index;
  return status;
}
API int CALL codex_agent_operation_destroy(void *c, void **slot) {
  (void)c;
  if (test_load(&fail_operation_destroy_once) != 0) {
    test_store(&fail_operation_destroy_once, 0);
    return 8;
  }
  int status = release_handle(slot);
  if (status == OK) test_decrement(&active_operations);
  return status;
}
API int CALL codex_agent_subscription_destroy(void *c, void **slot) {
  (void)c;
  if (slot == NULL) return 1;
  handle_t *subscription = (handle_t *)*slot;
  if (subscription == NULL) return OK;
  test_store(&subscription->cancel_requested, 1);
  if (subscription->busy_remaining > 0) {
    subscription->busy_remaining--;
    return BUSY;
  }
  if (test_load(&subscription->worker_complete) == 0) return BUSY;
  if (subscription->has_worker != 0) {
#if defined(_WIN32)
    if (WaitForSingleObject(subscription->worker, INFINITE) != WAIT_OBJECT_0) return 8;
    CloseHandle(subscription->worker);
#else
    if (pthread_join(subscription->worker, NULL) != 0) return 8;
#endif
    subscription->has_worker = 0;
  }
  free(subscription);
  *slot = NULL;
  test_decrement(&active_subscriptions);
  return OK;
}
API int CALL codex_agent_snapshot_destroy(void *c, void **slot) {
  (void)c;
  return release_handle(slot);
}

API int CALL codex_agent_host_state_kind(void *c, void *snapshot, int32_t *kind) {
  (void)c; leaf_record("codex_agent_host_state_kind");
  if (snapshot == NULL || kind == NULL) return 1;
  *kind = ((handle_t *)snapshot)->result == 2 ? 6 : 4;
  return OK;
}
API int CALL codex_agent_host_state_agent(void *c, void *h, void *s, void **out) {
  (void)c; (void)h; (void)s;
  leaf_record("codex_agent_host_state_agent");
  test_store(&agent_released, 0);
  return snapshot_get(out, 21);
}
API int CALL codex_agent_host_state_failure(void *c, void *s, void **out) {
  (void)c; (void)s; (void)out; return NOT_READY;
}
API int CALL codex_agent_host_state_has_workspace(void *c, void *s, int32_t *has) {
  (void)c; if (s == NULL || has == NULL) return 1;
  *has = ((handle_t *)s)->result == 2 ? 0 : 1;
  return OK;
}
API int CALL codex_agent_host_state_workspace_path_copy(void *c, void *s, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)s; return copy_bytes("/workspace", b, n, r);
}
API int CALL codex_agent_host_state_workspace_display_name_copy(void *c, void *s, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)s; (void)b; (void)n; (void)r; return NOT_READY;
}
API int CALL codex_agent_host_state_requirement_reason(void *c, void *s, int32_t *reason) {
  (void)c; (void)s; if (reason == NULL) return 1; *reason = 0; return OK;
}
API int CALL codex_agent_host_state_requirement_message_copy(void *c, void *s, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)s; return copy_bytes("select workspace", b, n, r);
}
API int CALL codex_agent_active_conversation(void *c, void *v, void *s, void **out) {
  (void)c; (void)v; leaf_record("codex_agent_active_conversation");
  if (s != NULL && ((handle_t *)s)->result == 1) return NOT_READY;
  return snapshot_get(out, 20);
}
API int CALL codex_agent_conversation_state_status(void *c, void *s, int32_t *status) {
  (void)c; if (s == NULL || status == NULL) return 1;
  *status = ((handle_t *)s)->result == 0 ? 2 : ((handle_t *)s)->result == 1 ? 4 : 8;
  return OK;
}
API int CALL codex_agent_conversation_state_failure(void *c, void *s, void **out) {
  (void)c; (void)s; (void)out; return NOT_READY;
}
API int CALL codex_agent_state_boolean_value(void *c, void *s, int32_t *value) {
  (void)c; (void)s; leaf_record("codex_agent_state_boolean_value"); if (value == NULL) return 1; *value = ((handle_t *)s)->result == 2 ? 0 : 1; return OK;
}

API int CALL codex_agent_failure_release(void *c, void **slot) { (void)c; return release_handle(slot); }
API int CALL codex_agent_failure_code_copy(void *c, void *f, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)f; return copy_bytes("fake", b, n, r);
}
API int CALL codex_agent_failure_message_copy(void *c, void *f, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)f; return copy_bytes("fake failure", b, n, r);
}
API int CALL codex_agent_failure_is_recoverable(void *c, void *f, int32_t *value) {
  (void)c; (void)f; if (value == NULL) return 1; *value = 1; return OK;
}

API int CALL codex_agent_conversation_summary_destroy(void *c, void **slot) { (void)c; return release_handle(slot); }
API int CALL codex_agent_conversation_summary_conversation_id(void *c, void *s, void **out) {
  (void)c;
  int status = snapshot_get(out, 31);
  if (status == OK) {
    const char *value = ((handle_t *)s)->result == 0 ? "conversation-1" : "conversation-2";
    (void)strcpy(((handle_t *)*out)->text, value);
    ((handle_t *)*out)->busy_remaining = 0;
  }
  return status;
}
API int CALL codex_agent_conversation_summary_title_copy(void *c, void *s, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)s; return copy_bytes("Fixture", b, n, r);
}
API int CALL codex_agent_conversation_summary_updated_at_epoch_seconds(void *c, void *s, int64_t *value) {
  (void)c; if (value == NULL) return 1; *value = 1700000000 + ((handle_t *)s)->result; return OK;
}
API int CALL codex_agent_conversation_id_destroy(void *c, void **slot) { (void)c; return release_handle(slot); }
API int CALL codex_agent_conversation_id_value_copy(void *c, void *id, uint8_t *b, size_t n, size_t *r) {
  (void)c;
  return copy_bytes(((handle_t *)id)->text[0] == '\0' ? "conversation-1" : ((handle_t *)id)->text, b, n, r);
}
API int CALL codex_agent_conversation_id_create(void *c, const string_view_t *value, void **out) {
  (void)c;
  if (out == NULL || *out != NULL || value == NULL) return 1;
  handle_t *id = new_handle(31);
  if (id == NULL) return 2;
  if (copy_view(id->text, sizeof(id->text), value) != OK) { free(id); return 1; }
  id->busy_remaining = 0;
  *out = id;
  return OK;
}

API int CALL codex_agent_invocation_plugin_create(void *c, const string_view_t *name, const string_view_t *uri, void **out) {
  (void)c;
  if (out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(78);
  if (value == NULL) return 2;
  if (copy_view(value->text, sizeof(value->text), name) != OK ||
      copy_view(value->second, sizeof(value->second), uri) != OK) { free(value); return 1; }
  value->busy_remaining = 0;
  *out = value;
  return OK;
}
API int CALL codex_agent_invocation_skill_create(void *c, const string_view_t *name, const string_view_t *path, void **out) {
  (void)c;
  if (out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(79);
  if (value == NULL) return 2;
  if (copy_view(value->text, sizeof(value->text), name) != OK ||
      copy_view(value->second, sizeof(value->second), path) != OK) { free(value); return 1; }
  value->busy_remaining = 0;
  *out = value;
  return OK;
}
API int CALL codex_agent_invocation_plugin_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_invocation_skill_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_invocation_from_plugin(void *c, void *plugin, void **out) {
  (void)c;
  if (plugin == NULL || out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(80);
  if (value == NULL) return 2;
  value->busy_remaining = 0;
  value->result = 0;
  memcpy(value->text, ((handle_t *)plugin)->text, sizeof(value->text));
  memcpy(value->second, ((handle_t *)plugin)->second, sizeof(value->second));
  *out = value;
  return OK;
}
API int CALL codex_agent_invocation_from_skill(void *c, void *skill, void **out) {
  int status = codex_agent_invocation_from_plugin(c, skill, out);
  if (status == OK) ((handle_t *)*out)->result = 1;
  return status;
}
API int CALL codex_agent_invocation_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_invocation_kind(void *c, void *invocation, int32_t *kind) {
  (void)c; if (invocation == NULL || kind == NULL) return 1; *kind = ((handle_t *)invocation)->result; return OK;
}
API int CALL codex_agent_invocation_plugin(void *c, void *invocation, void **out) {
  (void)c;
  if (invocation == NULL || ((handle_t *)invocation)->result != 0 || out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(78);
  if (value == NULL) return 2;
  value->busy_remaining = 0;
  memcpy(value->text, ((handle_t *)invocation)->text, sizeof(value->text));
  memcpy(value->second, ((handle_t *)invocation)->second, sizeof(value->second));
  *out = value;
  return OK;
}
API int CALL codex_agent_invocation_skill(void *c, void *invocation, void **out) {
  (void)c;
  if (invocation == NULL || ((handle_t *)invocation)->result != 1 || out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(79);
  if (value == NULL) return 2;
  value->busy_remaining = 0;
  memcpy(value->text, ((handle_t *)invocation)->text, sizeof(value->text));
  memcpy(value->second, ((handle_t *)invocation)->second, sizeof(value->second));
  *out = value;
  return OK;
}
API int CALL codex_agent_invocation_plugin_name_copy(void *c, void *value, uint8_t *b, size_t n, size_t *r) {
  (void)c; return copy_bytes(((handle_t *)value)->text, b, n, r);
}
API int CALL codex_agent_invocation_plugin_uri_copy(void *c, void *value, uint8_t *b, size_t n, size_t *r) {
  (void)c; return copy_bytes(((handle_t *)value)->second, b, n, r);
}
API int CALL codex_agent_invocation_skill_name_copy(void *c, void *value, uint8_t *b, size_t n, size_t *r) {
  (void)c; return copy_bytes(((handle_t *)value)->text, b, n, r);
}
API int CALL codex_agent_invocation_skill_path_copy(void *c, void *value, uint8_t *b, size_t n, size_t *r) {
  (void)c; return copy_bytes(((handle_t *)value)->second, b, n, r);
}

API int CALL codex_agent_turn_request_create(
    void *c, const string_view_t *prompt,
    int32_t has_client_id, const string_view_t *client_id,
    int32_t has_model, const string_view_t *model,
    int32_t has_effort, const string_view_t *effort,
    int32_t has_tier, const string_view_t *tier,
    int32_t approval, const int32_t *capabilities, size_t capability_count,
    void *const *invocations, size_t invocation_count, int32_t mode, void **out) {
  (void)c;
  if (out == NULL || *out != NULL || !view_equals(prompt, "structured") ||
      has_client_id != 1 || !view_equals(client_id, "client-1") ||
      has_model != 1 || !view_equals(model, "gpt-test") ||
      has_effort != 1 || !view_equals(effort, "high") ||
      has_tier != 1 || !view_equals(tier, "priority") || approval != 2 || mode != 1 ||
      capability_count != 1 || capabilities == NULL || capabilities[0] != 0 ||
      invocation_count != 2 || invocations == NULL) return 1;
  handle_t *plugin = (handle_t *)invocations[0];
  handle_t *skill = (handle_t *)invocations[1];
  if (plugin == NULL || plugin->result != 0 || strcmp(plugin->text, "plugin") != 0 ||
      strcmp(plugin->second, "plugin://fixture") != 0 || skill == NULL ||
      skill->result != 1 || strcmp(skill->text, "skill") != 0 ||
      strcmp(skill->second, "/fixture/SKILL.md") != 0) return 1;
  handle_t *request = new_handle(82);
  if (request == NULL) return 2;
  request->busy_remaining = 0;
  request->result = 1;
  *out = request;
  return OK;
}
API int CALL codex_agent_turn_request_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }

API int CALL codex_agent_conversation_value_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_conversation_value_summary(void *c, void *value, void **out) {
  (void)c; (void)value;
  int status = snapshot_get(out, 30);
  if (status == OK) ((handle_t *)*out)->busy_remaining = 0;
  return status;
}
API int CALL codex_agent_conversation_value_messages_count(void *c, void *value, size_t *count) {
  (void)c; (void)value; if (count == NULL) return 1; *count = 2; return OK;
}
API int CALL codex_agent_conversation_value_message_at(void *c, void *value, size_t index, void **out) {
  (void)c; (void)value;
  if (index > 1) return 1;
  int status = snapshot_get(out, 63);
  if (status == OK) { ((handle_t *)*out)->busy_remaining = 0; ((handle_t *)*out)->result = (int)index; }
  return status;
}
API int CALL codex_agent_conversation_current_messages_count(void *c, void *snapshot, size_t *count) {
  (void)c;
  leaf_record("codex_agent_conversation_current_messages_count");
  if (snapshot == NULL || count == NULL) return 1;
  int transition = ((handle_t *)snapshot)->result;
  *count = transition == 0 ? 2u : transition == 1 ? 1u : 0u;
  return OK;
}
API int CALL codex_agent_conversation_current_messages_at(void *c, void *snapshot, size_t index, void **out) {
  (void)c;
  leaf_record("codex_agent_conversation_current_messages_at");
  if (snapshot == NULL || out == NULL || *out != NULL) return 1;
  int transition = ((handle_t *)snapshot)->result;
  size_t count = transition == 0 ? 2u : transition == 1 ? 1u : 0u;
  if (index >= count) return 1;
  handle_t *message = new_handle(63);
  if (message == NULL) return 2;
  message->busy_remaining = 0;
  message->result = (int)index + transition * 10;
  *out = message;
  return OK;
}
API int CALL codex_agent_message_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_message_id_copy(void *c, void *message, uint8_t *b, size_t n, size_t *r) {
  (void)c; int value = ((handle_t *)message)->result;
  return copy_bytes(value >= 10 ? "message-updated" : value == 0 ? "message-1" : "message-2", b, n, r);
}
API int CALL codex_agent_message_has_client_message_id(void *c, void *message, int32_t *out) {
  (void)c; if (out == NULL) return 1; *out = ((handle_t *)message)->result % 10 == 0; return OK;
}
API int CALL codex_agent_message_client_message_id_copy(void *c, void *message, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)message; return copy_bytes("client-message", b, n, r);
}
API int CALL codex_agent_message_role(void *c, void *message, int32_t *out) {
  (void)c; if (out == NULL) return 1; *out = ((handle_t *)message)->result % 10; return OK;
}
API int CALL codex_agent_message_text_copy(void *c, void *message, uint8_t *b, size_t n, size_t *r) {
  (void)c; int value = ((handle_t *)message)->result;
  return copy_bytes(value >= 10 ? "updated" : "duplicate", b, n, r);
}
API int CALL codex_agent_message_collaboration_mode(void *c, void *message, int32_t *out) {
  (void)c; if (out == NULL) return 1; *out = ((handle_t *)message)->result % 10; return OK;
}
API int CALL codex_agent_message_has_reasoning(void *c, void *message, int32_t *out) {
  (void)c; if (out == NULL) return 1; *out = ((handle_t *)message)->result % 10 == 0; return OK;
}
API int CALL codex_agent_message_reasoning_copy(void *c, void *message, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)message; return copy_bytes("reasoning", b, n, r);
}
API int CALL codex_agent_message_has_plan(void *c, void *message, int32_t *out) {
  (void)c; if (out == NULL) return 1; *out = ((handle_t *)message)->result % 10 == 1; return OK;
}
API int CALL codex_agent_message_plan_copy(void *c, void *message, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)message; return copy_bytes("plan", b, n, r);
}
API int CALL codex_agent_message_has_shell_command(void *c, void *message, int32_t *out) {
  (void)c; if (out == NULL) return 1; *out = ((handle_t *)message)->result % 10 == 0; return OK;
}
API int CALL codex_agent_message_shell_command_copy(void *c, void *message, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)message; return copy_bytes("pwd", b, n, r);
}
API int CALL codex_agent_message_exit_code(void *c, void *message, int32_t *has, int32_t *value) {
  (void)c; if (has == NULL || value == NULL) return 1; *has = ((handle_t *)message)->result % 10 == 0; *value = 7; return OK;
}
API int CALL codex_agent_message_capabilities_count(void *c, void *message, size_t *count) {
  (void)c; (void)message; if (count == NULL) return 1; *count = 1; return OK;
}
API int CALL codex_agent_message_has_capability(void *c, void *message, int32_t capability, int32_t *out) {
  (void)c; (void)message; if (out == NULL) return 1; *out = capability == 0; return OK;
}
API int CALL codex_agent_message_invocations_count(void *c, void *message, size_t *count) {
  (void)c; (void)message; if (count == NULL) return 1; *count = 2; return OK;
}
API int CALL codex_agent_message_invocation_at(void *c, void *message, size_t index, void **out) {
  (void)c; (void)message;
  if (index > 1 || out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(80);
  if (value == NULL) return 2;
  value->busy_remaining = 0;
  value->result = (int)index;
  strcpy(value->text, index == 0 ? "plugin" : "skill");
  strcpy(value->second, index == 0 ? "plugin://fixture" : "/fixture/SKILL.md");
  *out = value;
  return OK;
}

API int CALL codex_agent_conversation_active_turn_progress_has_value(void *c, void *snapshot, int32_t *out) {
  (void)c; leaf_record("codex_agent_conversation_active_turn_progress_has_value"); if (snapshot == NULL || out == NULL) return 1; *out = ((handle_t *)snapshot)->result != 0 && ((handle_t *)snapshot)->result != 2; return OK;
}
API int CALL codex_agent_conversation_active_turn_progress_value(void *c, void *snapshot, void **out) {
  (void)c;
  leaf_record("codex_agent_conversation_active_turn_progress_value");
  if (snapshot == NULL || (((handle_t *)snapshot)->result != 1 && ((handle_t *)snapshot)->result != 3 && ((handle_t *)snapshot)->result != 4) || out == NULL || *out != NULL) return NOT_READY;
  handle_t *value = new_handle(90);
  if (value == NULL) return 2;
  value->busy_remaining = 0;
  value->result = ((handle_t *)snapshot)->result;
  *out = value;
  return OK;
}
API int CALL codex_agent_turn_progress_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
#define PROGRESS_COPY(name, value) API int CALL name(void *c, void *p, uint8_t *b, size_t n, size_t *r) { (void)c; (void)p; return copy_bytes(value, b, n, r); }
PROGRESS_COPY(codex_agent_turn_progress_text_copy, "text")
PROGRESS_COPY(codex_agent_turn_progress_commentary_copy, "commentary")
PROGRESS_COPY(codex_agent_turn_progress_reasoning_copy, "reasoning")
PROGRESS_COPY(codex_agent_turn_progress_plan_copy, "plan")
PROGRESS_COPY(codex_agent_turn_progress_shell_output_copy, "shell")
API int CALL codex_agent_turn_progress_has_plan_progress(void *c, void *p, int32_t *out) { (void)c; if (out == NULL) return 1; *out = ((handle_t *)p)->result != 4; return OK; }
API int CALL codex_agent_turn_progress_plan_progress(void *c, void *p, void **out) { (void)c; if (((handle_t *)p)->result == 4) return NOT_READY; int status = snapshot_get(out, 91); if (status == OK) { ((handle_t *)*out)->busy_remaining = 0; ((handle_t *)*out)->result = ((handle_t *)p)->result; } return status; }
API int CALL codex_agent_turn_progress_shell_exit_code(void *c, void *p, int32_t *has, int32_t *value) { (void)c; if (has == NULL || value == NULL) return 1; *has = ((handle_t *)p)->result == 1; *value = 9; return OK; }
API int CALL codex_agent_turn_progress_work_activity(void *c, void *p, int32_t *has, int32_t *value) { (void)c; if (has == NULL || value == NULL) return 1; *has = ((handle_t *)p)->result == 1; *value = 1; return OK; }
API int CALL codex_agent_turn_progress_hook_activities_count(void *c, void *p, size_t *count) { (void)c; (void)p; if (count == NULL) return 1; *count = 2; return OK; }
API int CALL codex_agent_turn_progress_hook_activity_at(void *c, void *p, size_t index, void **out) { (void)c; if (index > 1) return 1; int status = snapshot_get(out, 92); if (status == OK) { ((handle_t *)*out)->busy_remaining = 0; ((handle_t *)*out)->result = (int)index; if (((handle_t *)p)->result != 1) (void)strcpy(((handle_t *)*out)->second, "nested-absent"); } return status; }
API int CALL codex_agent_turn_progress_is_truncated(void *c, void *p, int32_t *out) { (void)c; (void)p; if (out == NULL) return 1; *out = 1; return OK; }

API int CALL codex_agent_plan_progress_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_plan_progress_has_explanation(void *c, void *p, int32_t *out) { (void)c; if (out == NULL) return 1; *out = ((handle_t *)p)->result == 1; return OK; }
API int CALL codex_agent_plan_progress_explanation_copy(void *c, void *p, uint8_t *b, size_t n, size_t *r) { (void)c; (void)p; return copy_bytes("explanation", b, n, r); }
API int CALL codex_agent_plan_progress_steps_count(void *c, void *p, size_t *count) { (void)c; (void)p; if (count == NULL) return 1; *count = 2; return OK; }
API int CALL codex_agent_plan_progress_step_at(void *c, void *p, size_t index, void **out) { (void)c; (void)p; if (index > 1) return 1; int status = snapshot_get(out, 93); if (status == OK) { ((handle_t *)*out)->busy_remaining = 0; ((handle_t *)*out)->result = (int)index; } return status; }
API int CALL codex_agent_plan_step_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_plan_step_text_copy(void *c, void *step, uint8_t *b, size_t n, size_t *r) { (void)c; (void)step; return copy_bytes("duplicate step", b, n, r); }
API int CALL codex_agent_plan_step_status(void *c, void *step, int32_t *out) { (void)c; if (out == NULL) return 1; *out = ((handle_t *)step)->result; return OK; }

API int CALL codex_agent_hook_activity_destroy(void *c, void **slot) { (void)c; return destroy_value(slot); }
API int CALL codex_agent_hook_activity_id_copy(void *c, void *activity, uint8_t *b, size_t n, size_t *r) { (void)c; return copy_bytes(((handle_t *)activity)->result == 0 ? "hook-1" : "hook-2", b, n, r); }
API int CALL codex_agent_hook_activity_event_name_copy(void *c, void *activity, uint8_t *b, size_t n, size_t *r) { (void)c; (void)activity; return copy_bytes("event", b, n, r); }
API int CALL codex_agent_hook_activity_handler_type_copy(void *c, void *activity, uint8_t *b, size_t n, size_t *r) { (void)c; (void)activity; return copy_bytes("command", b, n, r); }
API int CALL codex_agent_hook_activity_status(void *c, void *activity, int32_t *out) { (void)c; if (out == NULL) return 1; *out = ((handle_t *)activity)->result; return OK; }
API int CALL codex_agent_hook_activity_has_status_message(void *c, void *activity, int32_t *out) { (void)c; if (out == NULL) return 1; *out = ((handle_t *)activity)->second[0] == '\0'; return OK; }
API int CALL codex_agent_hook_activity_status_message_copy(void *c, void *activity, uint8_t *b, size_t n, size_t *r) { (void)c; (void)activity; return copy_bytes("status", b, n, r); }
API int CALL codex_agent_hook_activity_details_count(void *c, void *activity, size_t *count) { (void)c; (void)activity; if (count == NULL) return 1; *count = 2; return OK; }
API int CALL codex_agent_hook_activity_detail_copy_at(void *c, void *activity, size_t index, uint8_t *b, size_t n, size_t *r) { (void)c; (void)activity; if (index > 1) return 1; return copy_bytes("duplicate detail", b, n, r); }


/* Leaf-service fixture: every public call below is reached through the same
 * production Dart FFI field used with the real SDK. */
static int value_out(void **out, int kind) {
  if (out == NULL || *out != NULL) return 1;
  handle_t *value = new_handle(kind);
  if (value == NULL) return 2;
  value->busy_remaining = 0;
  *out = value;
  return OK;
}
static int value_release(void **slot) {
  if (slot == NULL) return 1;
  free(*slot);
  *slot = NULL;
  return OK;
}

#define LEAF_SERVICE(suffix) \
  API int CALL codex_agent_agent_##suffix(void *c, void *a, void **out) { \
    (void)c; (void)a; leaf_record("codex_agent_agent_" #suffix); return value_out(out, 60); \
  } \
  API int CALL codex_agent_##suffix##_release(void *c, void **slot) { \
    (void)c; leaf_record("codex_agent_" #suffix "_release"); return value_release(slot); \
  }
LEAF_SERVICE(authentication)
LEAF_SERVICE(interactions)
LEAF_SERVICE(integration_authorization)
LEAF_SERVICE(models)
LEAF_SERVICE(skills)
LEAF_SERVICE(hooks)
LEAF_SERVICE(plugins)
LEAF_SERVICE(connectors)
LEAF_SERVICE(mcp_servers)

#define AVAILABLE(name) \
  API int CALL name(void *c, void *service, int32_t *out) { \
    (void)c; (void)service; leaf_record(#name); \
    if (test_load(&agent_released) != 0) return 1; \
    if (out == NULL) return 1; *out = 1; return OK; \
  }
AVAILABLE(codex_agent_skills_is_available)
AVAILABLE(codex_agent_hooks_is_available)
AVAILABLE(codex_agent_plugins_is_available)
AVAILABLE(codex_agent_connectors_is_available)
AVAILABLE(codex_agent_mcp_servers_is_available)

#define LEAF_OP0(name, kind) \
  API int CALL name(void *c, void *s, operation_callback_t cb, void *u, void **out) { \
    (void)s; leaf_record(#name); \
    if (test_load(&agent_released) != 0) return 1; \
    return operation(c, cb, u, out, kind); \
  }
#define LEAF_OP_INT(name, kind) \
  API int CALL name(void *c, void *s, int32_t v, operation_callback_t cb, void *u, void **out) { \
    (void)s; (void)v; leaf_record(#name); return operation(c, cb, u, out, kind); \
  }
#define LEAF_OP_HANDLE(name, kind) \
  API int CALL name(void *c, void *s, void *v, operation_callback_t cb, void *u, void **out) { \
    (void)s; (void)v; leaf_record(#name); return operation(c, cb, u, out, kind); \
  }
#define LEAF_OP_HANDLE_INT(name, kind) \
  API int CALL name(void *c, void *s, void *v, int32_t i, operation_callback_t cb, void *u, void **out) { \
    (void)s; (void)v; (void)i; leaf_record(#name); return operation(c, cb, u, out, kind); \
  }
#define LEAF_OP_TWO_HANDLE(name, kind) \
  API int CALL name(void *c, void *s, void *a, void *b, operation_callback_t cb, void *u, void **out) { \
    (void)s; (void)a; (void)b; leaf_record(#name); return operation(c, cb, u, out, kind); \
  }

LEAF_OP_HANDLE(codex_agent_authentication_authenticate_api_key, 61)
LEAF_OP_HANDLE(codex_agent_authentication_authenticate_chat_gpt_browser, 62)
LEAF_OP_HANDLE(codex_agent_authentication_authenticate_chat_gpt_device_code, 63)
LEAF_OP0(codex_agent_authentication_cancel, 64)
LEAF_OP0(codex_agent_authentication_sign_out, 65)
LEAF_OP_HANDLE(codex_agent_integration_authorization_authorize, 66)
LEAF_OP0(codex_agent_integration_authorization_cancel, 67)
LEAF_OP0(codex_agent_models_list, 68)
LEAF_OP_INT(codex_agent_models_resolve, 69)
LEAF_OP_HANDLE_INT(codex_agent_models_resolve_effort, 70)
LEAF_OP_HANDLE_INT(codex_agent_models_resolve_service_tier, 71)
LEAF_OP_INT(codex_agent_skills_list, 72)
LEAF_OP_HANDLE(codex_agent_skills_uninstall, 73)
LEAF_OP0(codex_agent_hooks_list, 74)
LEAF_OP_HANDLE(codex_agent_hooks_uninstall, 75)
LEAF_OP_HANDLE(codex_agent_hooks_trust, 76)
LEAF_OP_INT(codex_agent_plugins_list, 77)
LEAF_OP_HANDLE(codex_agent_plugins_read, 78)
LEAF_OP_HANDLE(codex_agent_plugins_install, 79)
LEAF_OP_HANDLE(codex_agent_plugins_uninstall, 80)
LEAF_OP_INT(codex_agent_connectors_list, 81)
LEAF_OP0(codex_agent_mcp_servers_list, 82)
LEAF_OP_HANDLE(codex_agent_mcp_servers_add, 83)
LEAF_OP_HANDLE(codex_agent_mcp_servers_remove, 84)
LEAF_OP_HANDLE(codex_agent_interactions_open_url, 85)
LEAF_OP_HANDLE_INT(codex_agent_interactions_resolve_approval, 86)
LEAF_OP_TWO_HANDLE(codex_agent_interactions_resolve_elicitation, 87)

API int CALL codex_agent_skills_read(void *c, void *s, const string_view_t *path, int64_t offset, operation_callback_t cb, void *u, void **out) {
  (void)s; (void)path; (void)offset; leaf_record("codex_agent_skills_read"); return operation(c, cb, u, out, 88);
}
API int CALL codex_agent_skills_install(void *c, void *s, const string_view_t *path, int32_t scope, operation_callback_t cb, void *u, void **out) {
  (void)s; (void)path; (void)scope; leaf_record("codex_agent_skills_install"); return operation(c, cb, u, out, 89);
}
API int CALL codex_agent_hooks_install(void *c, void *s, const string_view_t *path, int32_t scope, operation_callback_t cb, void *u, void **out) {
  (void)s; (void)path; (void)scope; leaf_record("codex_agent_hooks_install"); return operation(c, cb, u, out, 90);
}

#define LEAF_FLOW(prefix, kind) \
  API int CALL prefix##_get(void *c, void *s, void **out) { \
    (void)c; (void)s; leaf_record(#prefix "_get"); \
    if (test_load(&agent_released) != 0) return 1; \
    return snapshot_get(out, kind); \
  } \
  API int CALL prefix##_subscribe(void *c, void *s, state_callback_t cb, void *u, void **out) { \
    (void)s; leaf_record(#prefix "_subscribe"); \
    if (test_load(&agent_released) != 0) return 1; \
    return subscribe(c, cb, u, out, kind); \
  }
LEAF_FLOW(codex_agent_authentication_state, 91)
LEAF_FLOW(codex_agent_authentication_is_authenticated, 92)
LEAF_FLOW(codex_agent_authentication_is_authenticating, 93)
LEAF_FLOW(codex_agent_integration_authorization_state, 94)
LEAF_FLOW(codex_agent_integration_authorization_active, 95)
LEAF_FLOW(codex_agent_integration_authorization_is_authorizing, 96)
LEAF_FLOW(codex_agent_interactions_state, 97)
LEAF_FLOW(codex_agent_interactions_approvals, 98)
LEAF_FLOW(codex_agent_interactions_elicitations, 99)

#define SNAPSHOT_VALUE(name, kind) \
  API int CALL name(void *c, void *s, void **out) { \
    (void)c; (void)s; leaf_record(#name); return value_out(out, kind); \
  }
SNAPSHOT_VALUE(codex_agent_authentication_state_value, 100)
SNAPSHOT_VALUE(codex_agent_integration_authorization_state_value, 101)
SNAPSHOT_VALUE(codex_agent_integration_authorization_active_value, 102)
SNAPSHOT_VALUE(codex_agent_interactions_state_value, 103)
API int CALL codex_agent_integration_authorization_active_has_value(void *c, void *s, int32_t *out) {
  (void)c; (void)s; leaf_record("codex_agent_integration_authorization_active_has_value");
  if (out == NULL) return 1; *out = 1; return OK;
}
API int CALL codex_agent_interactions_approvals_count(void *c, void *s, size_t *out) {
  (void)c; (void)s; leaf_record("codex_agent_interactions_approvals_count");
  if (out == NULL) return 1; *out = 1; return OK;
}
API int CALL codex_agent_interactions_approvals_at(void *c, void *s, size_t index, void **out) {
  (void)c; (void)s; leaf_record("codex_agent_interactions_approvals_at");
  if (index != 0) return 1; return value_out(out, 104);
}
API int CALL codex_agent_interactions_elicitations_count(void *c, void *s, size_t *out) {
  (void)c; (void)s; leaf_record("codex_agent_interactions_elicitations_count");
  if (out == NULL) return 1; *out = 1; return OK;
}
API int CALL codex_agent_interactions_elicitations_at(void *c, void *s, size_t index, void **out) {
  (void)c; (void)s; leaf_record("codex_agent_interactions_elicitations_at");
  if (index != 0) return 1; return value_out(out, 105);
}

/* The verified shared value bridge resolves its complete exact surface
 * eagerly. Only response_create/destroy execute in this leaf fixture; the
 * remaining symbols deliberately fail closed if an unintended path calls
 * them. */
#define LEAF_LOOKUP_STUB(name) API int CALL name(void) { return 1; }
LEAF_LOOKUP_STUB(codex_agent_form_boolean_value_create)
LEAF_LOOKUP_STUB(codex_agent_form_boolean_value_value)
LEAF_LOOKUP_STUB(codex_agent_form_number_value_create)
LEAF_LOOKUP_STUB(codex_agent_form_number_value_value)
LEAF_LOOKUP_STUB(codex_agent_form_text_value_create)
LEAF_LOOKUP_STUB(codex_agent_form_text_value_value_copy)
LEAF_LOOKUP_STUB(codex_agent_form_text_list_value_create)
LEAF_LOOKUP_STUB(codex_agent_form_text_list_value_count)
LEAF_LOOKUP_STUB(codex_agent_form_text_list_value_copy_at)
LEAF_LOOKUP_STUB(codex_agent_form_value_from_boolean)
LEAF_LOOKUP_STUB(codex_agent_form_value_from_number)
LEAF_LOOKUP_STUB(codex_agent_form_value_from_text)
LEAF_LOOKUP_STUB(codex_agent_form_value_from_text_list)
LEAF_LOOKUP_STUB(codex_agent_form_value_kind)
LEAF_LOOKUP_STUB(codex_agent_form_value_boolean)
LEAF_LOOKUP_STUB(codex_agent_form_value_number)
LEAF_LOOKUP_STUB(codex_agent_form_value_text)
LEAF_LOOKUP_STUB(codex_agent_form_value_text_list)
LEAF_LOOKUP_STUB(codex_agent_form_option_create)
LEAF_LOOKUP_STUB(codex_agent_form_field_create)
LEAF_LOOKUP_STUB(codex_agent_elicitation_create)
LEAF_LOOKUP_STUB(codex_agent_form_content_create)
LEAF_LOOKUP_STUB(codex_agent_form_content_count)
LEAF_LOOKUP_STUB(codex_agent_form_content_key_copy)
LEAF_LOOKUP_STUB(codex_agent_form_content_value_at)
LEAF_LOOKUP_STUB(codex_agent_elicitation_response_action)
LEAF_LOOKUP_STUB(codex_agent_elicitation_response_content_count)
LEAF_LOOKUP_STUB(codex_agent_elicitation_response_content_value)
LEAF_LOOKUP_STUB(codex_agent_elicitation_response_decline)
LEAF_LOOKUP_STUB(codex_agent_elicitation_response_cancel)
LEAF_LOOKUP_STUB(codex_agent_elicitation_initial_values)
LEAF_LOOKUP_STUB(codex_agent_elicitation_validate)
LEAF_LOOKUP_STUB(codex_agent_elicitation_accept)
LEAF_LOOKUP_STUB(codex_agent_elicitation_accepts)
LEAF_LOOKUP_STUB(codex_agent_form_field_accepts)
LEAF_LOOKUP_STUB(codex_agent_elicitation_validation_issue_count)
LEAF_LOOKUP_STUB(codex_agent_elicitation_validation_issue_at)
LEAF_LOOKUP_STUB(codex_agent_elicitation_validation_issue_field_name_copy)
LEAF_LOOKUP_STUB(codex_agent_elicitation_validation_issue_reason)
LEAF_LOOKUP_STUB(codex_agent_pending_approval_create)
LEAF_LOOKUP_STUB(codex_agent_pending_elicitation_create)
LEAF_LOOKUP_STUB(codex_agent_pending_interaction_from_approval)
LEAF_LOOKUP_STUB(codex_agent_pending_interaction_from_elicitation)
LEAF_LOOKUP_STUB(codex_agent_pending_interaction_request_id_copy)
LEAF_LOOKUP_STUB(codex_agent_pending_interaction_conversation_id)
LEAF_LOOKUP_STUB(codex_agent_failure_create)
LEAF_LOOKUP_STUB(codex_agent_interaction_state_create)
LEAF_LOOKUP_STUB(codex_agent_interaction_state_is_resolving)
LEAF_LOOKUP_STUB(codex_agent_interaction_state_pending_for)
LEAF_LOOKUP_STUB(codex_agent_pending_interaction_list_count)
LEAF_LOOKUP_STUB(codex_agent_pending_interaction_list_at)
LEAF_LOOKUP_STUB(codex_agent_authorization_url_chat_gpt)
LEAF_LOOKUP_STUB(codex_agent_authorization_url_external)
LEAF_LOOKUP_STUB(codex_agent_authorization_url_value_copy)
LEAF_LOOKUP_STUB(codex_agent_authorization_url_purpose)
#undef LEAF_LOOKUP_STUB

API int CALL codex_agent_elicitation_response_create(
  void *c,
  int32_t action,
  const string_view_t *keys,
  void **values,
  size_t count,
  void **out
) {
  (void)c; (void)action; (void)keys; (void)values; (void)count;
  return value_out(out, 106);
}
API int CALL codex_agent_elicitation_response_destroy(void *c, void **slot) {
  (void)c; return value_release(slot);
}

#define OP_COUNT(name, value) \
  API int CALL name(void *c, void *o, size_t *out) { \
    (void)c; (void)o; if (out == NULL) return 1; *out = value; return OK; \
  }
#define OP_AT(name, kind) \
  API int CALL name(void *c, void *o, size_t index, void **out) { \
    (void)c; (void)o; if (index > 1) return 1; return value_out(out, kind); \
  }
#define OP_VALUE(name, kind) \
  API int CALL name(void *c, void *o, void **out) { \
    (void)c; (void)o; return value_out(out, kind); \
  }
OP_COUNT(codex_agent_operation_models_count, 2)
OP_AT(codex_agent_operation_model_at, 110)
OP_VALUE(codex_agent_operation_model, 110)
OP_VALUE(codex_agent_operation_service_tier, 111)
OP_VALUE(codex_agent_operation_skill_catalog, 112)
OP_VALUE(codex_agent_operation_skill_chunk, 113)
OP_VALUE(codex_agent_operation_skill, 114)
OP_VALUE(codex_agent_operation_hook_catalog, 115)
OP_VALUE(codex_agent_operation_hook, 116)
OP_VALUE(codex_agent_operation_plugin_catalog, 117)
OP_VALUE(codex_agent_operation_plugin_detail, 118)
OP_VALUE(codex_agent_operation_plugin_install_result, 119)
OP_COUNT(codex_agent_operation_connectors_count, 2)
OP_AT(codex_agent_operation_connector_at, 120)
OP_COUNT(codex_agent_operation_mcp_servers_count, 2)
OP_AT(codex_agent_operation_mcp_server_at, 121)
OP_VALUE(codex_agent_operation_mcp_server, 121)
API int CALL codex_agent_operation_has_service_tier(void *c, void *o, int32_t *out) {
  (void)c; (void)o; if (out == NULL) return 1; *out = 1; return OK;
}
API int CALL codex_agent_operation_string_copy(void *c, void *o, uint8_t *b, size_t n, size_t *r) {
  (void)c; (void)o; return copy_bytes("high", b, n, r);
}

#define VALUE_RELEASE(name) \
  API int CALL name(void *c, void **slot) { (void)c; return value_release(slot); }
#define VALUE_STRING(name, text) \
  API int CALL name(void *c, void *v, uint8_t *b, size_t n, size_t *r) { \
    (void)c; (void)v; return copy_bytes(text, b, n, r); \
  }
#define VALUE_INT(name, result_value) \
  API int CALL name(void *c, void *v, int32_t *out) { \
    (void)c; (void)v; if (out == NULL) return 1; *out = result_value; return OK; \
  }
#define VALUE_I64(name, result_value) \
  API int CALL name(void *c, void *v, int64_t *out) { \
    (void)c; (void)v; if (out == NULL) return 1; *out = result_value; return OK; \
  }
#define VALUE_COUNT(name, result_value) \
  API int CALL name(void *c, void *v, size_t *out) { \
    (void)c; (void)v; if (out == NULL) return 1; *out = result_value; return OK; \
  }
#define VALUE_AT(name, kind) \
  API int CALL name(void *c, void *v, size_t index, void **out) { \
    (void)c; (void)v; (void)index; return value_out(out, kind); \
  }
#define VALUE_STRING_AT(name, text) \
  API int CALL name(void *c, void *v, size_t index, uint8_t *b, size_t n, size_t *r) { \
    (void)c; (void)v; (void)index; return copy_bytes(text, b, n, r); \
  }

VALUE_RELEASE(codex_agent_service_tier_destroy)
VALUE_STRING(codex_agent_service_tier_id_copy, "tier")
VALUE_STRING(codex_agent_service_tier_name_copy, "Tier")
VALUE_STRING(codex_agent_service_tier_description_copy, "fixture tier")
VALUE_RELEASE(codex_agent_model_destroy)
VALUE_STRING(codex_agent_model_id_copy, "model")
VALUE_STRING(codex_agent_model_display_name_copy, "Fixture model")
VALUE_STRING(codex_agent_model_description_copy, "fixture model description")
VALUE_COUNT(codex_agent_model_supported_efforts_count, 2)
VALUE_STRING_AT(codex_agent_model_supported_effort_copy_at, "high")
VALUE_STRING(codex_agent_model_default_effort_copy, "high")
VALUE_INT(codex_agent_model_is_default, 1)
VALUE_COUNT(codex_agent_model_service_tiers_count, 1)
VALUE_AT(codex_agent_model_service_tier_at, 111)
VALUE_INT(codex_agent_model_has_default_service_tier, 1)
VALUE_STRING(codex_agent_model_default_service_tier_copy, "tier")

VALUE_RELEASE(codex_agent_connector_destroy)
VALUE_STRING(codex_agent_connector_id_copy, "connector")
VALUE_STRING(codex_agent_connector_name_copy, "Fixture connector")
VALUE_STRING(codex_agent_connector_description_copy, "fixture connector description")
VALUE_INT(codex_agent_connector_has_install_url, 0)
VALUE_INT(codex_agent_connector_is_accessible, 1)
VALUE_INT(codex_agent_connector_is_enabled, 1)
VALUE_COUNT(codex_agent_connector_plugin_names_count, 2)
VALUE_STRING_AT(codex_agent_connector_plugin_names_copy_at, "fixture-plugin")

VALUE_RELEASE(codex_agent_plugin_reference_destroy)
VALUE_STRING(codex_agent_plugin_reference_id_copy, "plugin-id")
VALUE_STRING(codex_agent_plugin_reference_name_copy, "plugin")
VALUE_STRING(codex_agent_plugin_reference_marketplace_name_copy, "marketplace")
VALUE_INT(codex_agent_plugin_reference_has_marketplace_path, 0)
VALUE_INT(codex_agent_plugin_reference_has_remote_plugin_id, 0)
VALUE_RELEASE(codex_agent_plugin_skill_destroy)
VALUE_STRING(codex_agent_plugin_skill_name_copy, "plugin-skill")
VALUE_STRING(codex_agent_plugin_skill_description_copy, "fixture plugin skill")
VALUE_INT(codex_agent_plugin_skill_is_enabled, 1)
VALUE_INT(codex_agent_plugin_skill_has_path, 0)
VALUE_RELEASE(codex_agent_plugin_summary_destroy)
OP_VALUE(codex_agent_plugin_summary_reference, 130)
VALUE_STRING(codex_agent_plugin_summary_display_name_copy, "Fixture plugin")
VALUE_STRING(codex_agent_plugin_summary_description_copy, "fixture plugin description")
VALUE_INT(codex_agent_plugin_summary_is_installed, 1)
VALUE_INT(codex_agent_plugin_summary_is_enabled, 1)
VALUE_INT(codex_agent_plugin_summary_install_policy, 1)
VALUE_INT(codex_agent_plugin_summary_auth_policy, 0)
VALUE_INT(codex_agent_plugin_summary_is_available, 1)
VALUE_COUNT(codex_agent_plugin_summary_capabilities_count, 2)
VALUE_STRING_AT(codex_agent_plugin_summary_capabilities_copy_at, "capability")
VALUE_INT(codex_agent_plugin_summary_has_brand_color, 0)
VALUE_INT(codex_agent_plugin_summary_has_privacy_policy_url, 0)
VALUE_INT(codex_agent_plugin_summary_has_terms_of_service_url, 0)
VALUE_INT(codex_agent_plugin_summary_has_website_url, 0)
VALUE_RELEASE(codex_agent_plugin_catalog_destroy)
VALUE_COUNT(codex_agent_plugin_catalog_plugins_count, 2)
VALUE_AT(codex_agent_plugin_catalog_plugins_at, 131)
VALUE_COUNT(codex_agent_plugin_catalog_errors_count, 0)
VALUE_STRING_AT(codex_agent_plugin_catalog_errors_copy_at, "")
VALUE_INT(codex_agent_plugin_catalog_freshness, 0)
VALUE_RELEASE(codex_agent_plugin_detail_destroy)
OP_VALUE(codex_agent_plugin_detail_summary, 131)
VALUE_STRING(codex_agent_plugin_detail_description_copy, "fixture detail")
VALUE_COUNT(codex_agent_plugin_detail_skills_count, 1)
VALUE_AT(codex_agent_plugin_detail_skills_at, 132)
VALUE_COUNT(codex_agent_plugin_detail_connectors_count, 1)
VALUE_AT(codex_agent_plugin_detail_connectors_at, 120)
VALUE_COUNT(codex_agent_plugin_detail_mcp_servers_count, 1)
VALUE_STRING_AT(codex_agent_plugin_detail_mcp_servers_copy_at, "server")
VALUE_INT(codex_agent_plugin_detail_hook_count, 1)
VALUE_RELEASE(codex_agent_plugin_install_result_destroy)
VALUE_INT(codex_agent_plugin_install_result_auth_policy, 0)
VALUE_COUNT(codex_agent_plugin_install_result_connectors_count, 1)
VALUE_AT(codex_agent_plugin_install_result_connectors_at, 120)
VALUE_INT(codex_agent_plugin_install_result_has_message, 1)
VALUE_STRING(codex_agent_plugin_install_result_message_copy, "installed")

VALUE_RELEASE(codex_agent_skill_destroy)
VALUE_STRING(codex_agent_skill_name_copy, "skill")
VALUE_STRING(codex_agent_skill_display_name_copy, "Fixture skill")
VALUE_STRING(codex_agent_skill_description_copy, "fixture skill description")
VALUE_STRING(codex_agent_skill_path_copy, "/fixture/skill")
VALUE_INT(codex_agent_skill_scope, 1)
VALUE_INT(codex_agent_skill_is_enabled, 1)
VALUE_INT(codex_agent_skill_has_brand_color, 0)
VALUE_COUNT(codex_agent_skill_dependencies_count, 2)
VALUE_STRING_AT(codex_agent_skill_dependencies_copy_at, "dependency")
VALUE_INT(codex_agent_skill_can_uninstall, 1)
VALUE_INT(codex_agent_skill_origin, 0)
VALUE_RELEASE(codex_agent_skill_catalog_destroy)
VALUE_COUNT(codex_agent_skill_catalog_skills_count, 2)
VALUE_AT(codex_agent_skill_catalog_skills_at, 114)
VALUE_COUNT(codex_agent_skill_catalog_errors_count, 0)
VALUE_STRING_AT(codex_agent_skill_catalog_errors_copy_at, "")
VALUE_RELEASE(codex_agent_skill_chunk_destroy)
VALUE_STRING(codex_agent_skill_chunk_content_copy, "fixture skill content")
API int CALL codex_agent_skill_chunk_next_offset(void *c, void *v, int32_t *present, int64_t *out) {
  (void)c; (void)v; if (present == NULL || out == NULL) return 1; *present = 1; *out = 17; return OK;
}
VALUE_I64(codex_agent_skill_chunk_total_bytes, 34)

VALUE_RELEASE(codex_agent_hook_catalog_destroy)
VALUE_COUNT(codex_agent_hook_catalog_hooks_count, 1)
VALUE_AT(codex_agent_hook_catalog_hooks_at, 140)
VALUE_COUNT(codex_agent_hook_catalog_warnings_count, 0)
VALUE_STRING_AT(codex_agent_hook_catalog_warnings_copy_at, "")
VALUE_COUNT(codex_agent_hook_catalog_errors_count, 0)
VALUE_STRING_AT(codex_agent_hook_catalog_errors_copy_at, "")
VALUE_RELEASE(codex_agent_hook_destroy)
VALUE_STRING(codex_agent_hook_key_copy, "fixture-hook")
VALUE_STRING(codex_agent_hook_current_hash_copy, "hash")
VALUE_INT(codex_agent_hook_is_enabled, 1)
VALUE_STRING(codex_agent_hook_event_name_copy, "sessionStart")
OP_VALUE(codex_agent_hook_handler, 141)
VALUE_INT(codex_agent_hook_is_managed, 0)
VALUE_STRING(codex_agent_hook_source_copy, "USER")
VALUE_STRING(codex_agent_hook_source_path_copy, "/fixture/hook")
VALUE_I64(codex_agent_hook_timeout_seconds, 17)
VALUE_INT(codex_agent_hook_trust_status, 2)
VALUE_INT(codex_agent_hook_has_matcher, 0)
VALUE_INT(codex_agent_hook_has_plugin_id, 0)
VALUE_INT(codex_agent_hook_has_status_message, 0)
VALUE_INT(codex_agent_hook_origin, 0)
VALUE_INT(codex_agent_hook_can_uninstall, 1)
VALUE_RELEASE(codex_agent_hook_handler_destroy)
VALUE_INT(codex_agent_hook_handler_kind, 0)
OP_VALUE(codex_agent_hook_handler_agent, 142)
VALUE_RELEASE(codex_agent_hook_handler_agent_destroy)

VALUE_RELEASE(codex_agent_authentication_state_destroy)
VALUE_INT(codex_agent_authentication_state_status, 2)
VALUE_INT(codex_agent_authentication_state_has_pending_sign_in_url, 0)
VALUE_INT(codex_agent_authentication_state_has_device_verification_url, 0)
VALUE_INT(codex_agent_authentication_state_has_device_user_code, 0)
VALUE_INT(codex_agent_authentication_state_has_failure, 0)

VALUE_RELEASE(codex_agent_integration_authorization_state_destroy)
VALUE_INT(codex_agent_integration_authorization_state_status, 0)
API int CALL codex_agent_integration_authorization_state_target(void *c, void *v, void **out) {
  (void)c; (void)v; (void)out; return NOT_READY;
}
API int CALL codex_agent_integration_authorization_state_failure(void *c, void *v, void **out) {
  (void)c; (void)v; (void)out; return NOT_READY;
}
VALUE_RELEASE(codex_agent_integration_destroy)
VALUE_INT(codex_agent_integration_kind, 0)
OP_VALUE(codex_agent_integration_connector, 150)
VALUE_RELEASE(codex_agent_integration_connector_destroy)
OP_VALUE(codex_agent_integration_connector_connector, 120)

VALUE_RELEASE(codex_agent_interaction_state_destroy)
VALUE_COUNT(codex_agent_interaction_state_pending_count, 0)
VALUE_COUNT(codex_agent_interaction_state_resolving_request_ids_count, 0)
VALUE_INT(codex_agent_interaction_state_has_failure, 0)
API int CALL codex_agent_interaction_state_resolving_request_ids_contains(void *c, void *v, const string_view_t *s, int32_t *out) {
  (void)c; (void)v; (void)s; if (out == NULL) return 1; *out = 0; return OK;
}

VALUE_RELEASE(codex_agent_pending_approval_destroy)
VALUE_STRING(codex_agent_pending_approval_request_id_copy, "approval-1")
OP_VALUE(codex_agent_pending_approval_conversation_id, 31)
VALUE_STRING(codex_agent_pending_approval_title_copy, "Approve fixture")
VALUE_STRING(codex_agent_pending_approval_details_copy, "fixture details")
VALUE_RELEASE(codex_agent_pending_elicitation_destroy)
OP_VALUE(codex_agent_pending_elicitation_elicitation, 151)
VALUE_RELEASE(codex_agent_elicitation_destroy)
VALUE_STRING(codex_agent_elicitation_request_id_copy, "elicitation-1")
VALUE_STRING(codex_agent_elicitation_server_name_copy, "fixture-server")
OP_VALUE(codex_agent_elicitation_conversation_id, 31)
VALUE_STRING(codex_agent_elicitation_message_copy, "fixture question")
VALUE_INT(codex_agent_elicitation_has_form, 0)
VALUE_INT(codex_agent_elicitation_has_url, 1)
VALUE_STRING(codex_agent_elicitation_url_copy, "https://example.test/question")

VALUE_RELEASE(codex_agent_mcp_server_destroy)
VALUE_STRING(codex_agent_mcp_server_name_copy, "fixture_server")
VALUE_STRING(codex_agent_mcp_server_display_name_copy, "Fixture server")
VALUE_INT(codex_agent_mcp_server_auth_status, 4)
VALUE_INT(codex_agent_mcp_server_has_configuration, 0)
VALUE_INT(codex_agent_mcp_server_origin, 0)
VALUE_INT(codex_agent_mcp_server_can_remove, 1)

#define CREATE_CONTEXT_ONLY(name, kind) \
  API int CALL name(void *c, void **out) { (void)c; return value_out(out, kind); }
#define CREATE_STRING(name, kind) \
  API int CALL name(void *c, const string_view_t *v, void **out) { \
    (void)c; (void)v; return value_out(out, kind); \
  }
CREATE_STRING(codex_agent_authentication_method_api_key_create, 160)
CREATE_CONTEXT_ONLY(codex_agent_authentication_method_chat_gpt_browser_create, 161)
CREATE_CONTEXT_ONLY(codex_agent_authentication_method_chat_gpt_device_code_create, 162)
VALUE_RELEASE(codex_agent_authentication_method_api_key_destroy)
VALUE_RELEASE(codex_agent_authentication_method_chat_gpt_browser_destroy)
VALUE_RELEASE(codex_agent_authentication_method_chat_gpt_device_code_destroy)

API int CALL codex_agent_service_tier_create(void *c, const string_view_t *id, const string_view_t *name, const string_view_t *description, void **out) {
  (void)c; (void)id; (void)name; (void)description; return value_out(out, 111);
}
API int CALL codex_agent_model_create(void *c, const string_view_t *id, const string_view_t *display, const string_view_t *description, const string_view_t *efforts, size_t effort_count, const string_view_t *default_effort, int32_t is_default, void *const *tiers, size_t tier_count, int32_t has_default_tier, const string_view_t *default_tier, void **out) {
  (void)c; (void)id; (void)display; (void)description; (void)efforts; (void)effort_count; (void)default_effort; (void)is_default; (void)tiers; (void)tier_count; (void)has_default_tier; (void)default_tier; return value_out(out, 110);
}
API int CALL codex_agent_plugin_reference_create(void *c, const string_view_t *id, const string_view_t *name, const string_view_t *marketplace, int32_t has_path, const string_view_t *path, int32_t has_remote, const string_view_t *remote, void **out) {
  (void)c; (void)id; (void)name; (void)marketplace; (void)has_path; (void)path; (void)has_remote; (void)remote; return value_out(out, 130);
}
API int CALL codex_agent_skill_create(void *c, const string_view_t *name, const string_view_t *display, const string_view_t *description, const string_view_t *path, int32_t scope, int32_t enabled, int32_t has_brand, const string_view_t *brand, const string_view_t *dependencies, size_t dependency_count, int32_t can_uninstall, int32_t has_origin, int32_t origin, void **out) {
  (void)c; (void)name; (void)display; (void)description; (void)path; (void)scope; (void)enabled; (void)has_brand; (void)brand; (void)dependencies; (void)dependency_count; (void)can_uninstall; (void)has_origin; (void)origin; return value_out(out, 114);
}
API int CALL codex_agent_connector_create(void *c, const string_view_t *id, const string_view_t *name, const string_view_t *description, int32_t has_install, const string_view_t *install, int32_t accessible, int32_t enabled, const string_view_t *plugins, size_t plugin_count, void **out) {
  (void)c; (void)id; (void)name; (void)description; (void)has_install; (void)install; (void)accessible; (void)enabled; (void)plugins; (void)plugin_count; return value_out(out, 120);
}

CREATE_CONTEXT_ONLY(codex_agent_hook_handler_agent_acquire, 142)
CREATE_CONTEXT_ONLY(codex_agent_hook_handler_prompt_acquire, 143)
VALUE_RELEASE(codex_agent_hook_handler_prompt_destroy)
API int CALL codex_agent_hook_handler_command_create(void *c, const string_view_t *command, int32_t is_async, void **out) {
  (void)c; (void)command; (void)is_async; return value_out(out, 144);
}
VALUE_RELEASE(codex_agent_hook_handler_command_destroy)
API int CALL codex_agent_hook_handler_mcp_tool_create(void *c, const string_view_t *server, const string_view_t *tool, void **out) {
  (void)c; (void)server; (void)tool; return value_out(out, 145);
}
VALUE_RELEASE(codex_agent_hook_handler_mcp_tool_destroy)
#define WRAP_HANDLE(name, kind) \
  API int CALL name(void *c, void *v, void **out) { \
    (void)c; (void)v; return value_out(out, kind); \
  }
WRAP_HANDLE(codex_agent_hook_handler_from_agent, 141)
WRAP_HANDLE(codex_agent_hook_handler_from_prompt, 141)
WRAP_HANDLE(codex_agent_hook_handler_from_command, 141)
WRAP_HANDLE(codex_agent_hook_handler_from_mcp_tool, 141)
API int CALL codex_agent_hook_create(void *c, const string_view_t *key, const string_view_t *hash, int32_t enabled, const string_view_t *event, void *handler, int32_t managed, const string_view_t *source, const string_view_t *source_path, int64_t timeout, int32_t trust, int32_t has_matcher, const string_view_t *matcher, int32_t has_plugin, const string_view_t *plugin, int32_t has_status, const string_view_t *status, int32_t has_origin, int32_t origin, int32_t can_uninstall, void **out) {
  (void)c; (void)key; (void)hash; (void)enabled; (void)event; (void)handler; (void)managed; (void)source; (void)source_path; (void)timeout; (void)trust; (void)has_matcher; (void)matcher; (void)has_plugin; (void)plugin; (void)has_status; (void)status; (void)has_origin; (void)origin; (void)can_uninstall; return value_out(out, 140);
}

API int CALL codex_agent_mcp_environment_variable_create(void *c, const string_view_t *name, int32_t has_source, int32_t source, void **out) {
  (void)c; (void)name; (void)has_source; (void)source; return value_out(out, 170);
}
VALUE_RELEASE(codex_agent_mcp_environment_variable_destroy)
API int CALL codex_agent_mcp_oauth_configuration_create(void *c, int32_t has_client, const string_view_t *client, int32_t has_port, int32_t port, void **out) {
  (void)c; (void)has_client; (void)client; (void)has_port; (void)port; return value_out(out, 171);
}
VALUE_RELEASE(codex_agent_mcp_oauth_configuration_destroy)
API int CALL codex_agent_mcp_tool_configuration_create(void *c, int32_t has_approval, int32_t approval, void **out) {
  (void)c; (void)has_approval; (void)approval; return value_out(out, 172);
}
VALUE_RELEASE(codex_agent_mcp_tool_configuration_destroy)
API int CALL codex_agent_mcp_transport_http_create(void *c, const string_view_t *url, int32_t has_bearer, const string_view_t *bearer, int32_t has_headers, const string_view_t *header_keys, const string_view_t *header_values, size_t header_count, int32_t has_environment, const string_view_t *environment_keys, const string_view_t *environment_values, size_t environment_count, int32_t has_helper, const string_view_t *helper, void **out) {
  (void)c; (void)url; (void)has_bearer; (void)bearer; (void)has_headers; (void)header_keys; (void)header_values; (void)header_count; (void)has_environment; (void)environment_keys; (void)environment_values; (void)environment_count; (void)has_helper; (void)helper; return value_out(out, 173);
}
VALUE_RELEASE(codex_agent_mcp_transport_http_destroy)
API int CALL codex_agent_mcp_transport_stdio_create(void *c, const string_view_t *command, const string_view_t *arguments, size_t argument_count, int32_t has_directory, const string_view_t *directory, int32_t has_environment, const string_view_t *environment_keys, const string_view_t *environment_values, size_t environment_count, void *const *forwarded, size_t forwarded_count, void **out) {
  (void)c; (void)command; (void)arguments; (void)argument_count; (void)has_directory; (void)directory; (void)has_environment; (void)environment_keys; (void)environment_values; (void)environment_count; (void)forwarded; (void)forwarded_count; return value_out(out, 174);
}
VALUE_RELEASE(codex_agent_mcp_transport_stdio_destroy)
WRAP_HANDLE(codex_agent_mcp_transport_from_http, 175)
WRAP_HANDLE(codex_agent_mcp_transport_from_stdio, 175)
VALUE_RELEASE(codex_agent_mcp_transport_destroy)
API int CALL codex_agent_mcp_server_configuration_create(void *c, const string_view_t *name, void *transport, int32_t has_authentication, int32_t authentication, const string_view_t *environment_id, int32_t enabled, int32_t required, int32_t parallel, int32_t has_omit, const int32_t *omit, size_t omit_count, int32_t has_startup, double startup, int32_t has_tool_timeout, double tool_timeout, int32_t has_default_approval, int32_t default_approval, int32_t has_enabled, const string_view_t *enabled_tools, size_t enabled_count, int32_t has_disabled, const string_view_t *disabled_tools, size_t disabled_count, int32_t has_scopes, const string_view_t *scopes, size_t scope_count, int32_t has_oauth, void *oauth, int32_t has_oauth_resource, const string_view_t *oauth_resource, const string_view_t *tool_keys, void *const *tools, size_t tool_count, void **out) {
  (void)c; (void)name; (void)transport; (void)has_authentication; (void)authentication; (void)environment_id; (void)enabled; (void)required; (void)parallel; (void)has_omit; (void)omit; (void)omit_count; (void)has_startup; (void)startup; (void)has_tool_timeout; (void)tool_timeout; (void)has_default_approval; (void)default_approval; (void)has_enabled; (void)enabled_tools; (void)enabled_count; (void)has_disabled; (void)disabled_tools; (void)disabled_count; (void)has_scopes; (void)scopes; (void)scope_count; (void)has_oauth; (void)oauth; (void)has_oauth_resource; (void)oauth_resource; (void)tool_keys; (void)tools; (void)tool_count; return value_out(out, 176);
}
VALUE_RELEASE(codex_agent_mcp_server_configuration_destroy)
API int CALL codex_agent_mcp_server_create(void *c, const string_view_t *name, const string_view_t *display, int32_t auth_status, void *configuration, int32_t origin, int32_t can_remove, void **out) {
  (void)c; (void)name; (void)display; (void)auth_status; (void)configuration; (void)origin; (void)can_remove; return value_out(out, 121);
}
WRAP_HANDLE(codex_agent_integration_connector_create, 150)
WRAP_HANDLE(codex_agent_integration_from_connector, 152)
WRAP_HANDLE(codex_agent_integration_mcp_server_create, 153)
VALUE_RELEASE(codex_agent_integration_mcp_server_destroy)
WRAP_HANDLE(codex_agent_integration_from_mcp_server, 154)
