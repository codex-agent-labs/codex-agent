#include "codex_agent.h"

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #condition);                \
            return 1;                                                                               \
        }                                                                                           \
    } while (0)

#define LITERAL_VIEW(value)                                                                         \
    { (const uint8_t *)(value), sizeof(value) - 1u }

#define CHECK_COPY(function, context, handle, expected)                                              \
    do {                                                                                            \
        size_t required_ = SIZE_MAX;                                                                \
        uint8_t buffer_[128];                                                                       \
        CHECK(function((context), (handle), NULL, 0u, &required_) ==                                \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                                 \
        CHECK(required_ == sizeof(expected) - 1u);                                                   \
        CHECK(function((context), (handle), buffer_, sizeof(buffer_), &required_) ==                 \
              CODEX_AGENT_STATUS_OK);                                                               \
        CHECK(memcmp(buffer_, (expected), sizeof(expected) - 1u) == 0);                             \
    } while (0)

#define CHECK_COPY_AT(function, context, handle, index, expected)                                    \
    do {                                                                                            \
        size_t required_ = SIZE_MAX;                                                                \
        uint8_t buffer_[128];                                                                       \
        CHECK(function((context), (handle), (index), NULL, 0u, &required_) ==                       \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                                 \
        CHECK(required_ == sizeof(expected) - 1u);                                                   \
        CHECK(function((context), (handle), (index), buffer_, sizeof(buffer_), &required_) ==        \
              CODEX_AGENT_STATUS_OK);                                                               \
        CHECK(memcmp(buffer_, (expected), sizeof(expected) - 1u) == 0);                             \
    } while (0)

int main(void) {
    codex_agent_context_t *context = NULL;
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);

    codex_agent_string_view_t tier_fast_id = LITERAL_VIEW("fast");
    codex_agent_string_view_t tier_fast_name = LITERAL_VIEW("Fast");
    codex_agent_string_view_t tier_fast_description = LITERAL_VIEW("Low latency");
    codex_agent_string_view_t tier_flex_id = LITERAL_VIEW("flex");
    codex_agent_string_view_t tier_flex_name = LITERAL_VIEW("Flex");
    codex_agent_string_view_t tier_flex_description = LITERAL_VIEW("Lower cost");
    codex_agent_service_tier_t *fast = NULL;
    codex_agent_service_tier_t *flex = NULL;
    CHECK(codex_agent_service_tier_create(
              context, &tier_fast_id, &tier_fast_name, &tier_fast_description, &fast) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_service_tier_create(
              context, &tier_flex_id, &tier_flex_name, &tier_flex_description, &flex) ==
          CODEX_AGENT_STATUS_OK);

    uint8_t model_id_bytes[] = {'m', 'o', 'd', 'e', 'l'};
    codex_agent_string_view_t model_id = {model_id_bytes, sizeof(model_id_bytes)};
    codex_agent_string_view_t model_name = LITERAL_VIEW("Model");
    codex_agent_string_view_t model_description = LITERAL_VIEW("Description");
    codex_agent_string_view_t efforts[] = {
        LITERAL_VIEW("low"),
        LITERAL_VIEW("high"),
        LITERAL_VIEW("low"),
    };
    codex_agent_string_view_t default_effort = LITERAL_VIEW("medium");
    codex_agent_service_tier_t *tiers[] = {fast, flex, fast};
    codex_agent_string_view_t default_tier = LITERAL_VIEW("fast");
    codex_agent_model_t *model = NULL;
    CHECK(codex_agent_model_create(
              context,
              &model_id,
              &model_name,
              &model_description,
              efforts,
              3u,
              &default_effort,
              1,
              tiers,
              3u,
              1,
              &default_tier,
              &model) == CODEX_AGENT_STATUS_OK);
    model_id_bytes[0] = 'X';
    tiers[0] = flex;
    CHECK(codex_agent_service_tier_destroy(context, &fast) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_service_tier_destroy(context, &flex) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_model_id_copy, context, model, "model");
    CHECK_COPY(codex_agent_model_display_name_copy, context, model, "Model");
    CHECK_COPY(codex_agent_model_description_copy, context, model, "Description");
    size_t count = SIZE_MAX;
    CHECK(codex_agent_model_supported_efforts_count(context, model, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_model_supported_effort_copy_at, context, model, 0u, "low");
    CHECK_COPY_AT(codex_agent_model_supported_effort_copy_at, context, model, 1u, "high");
    CHECK_COPY_AT(codex_agent_model_supported_effort_copy_at, context, model, 2u, "low");
    CHECK_COPY(codex_agent_model_default_effort_copy, context, model, "medium");
    int32_t scalar = INT32_MIN;
    CHECK(codex_agent_model_is_default(context, model, &scalar) == CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 1);
    CHECK(codex_agent_model_service_tiers_count(context, model, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    codex_agent_service_tier_t *returned_tier = NULL;
    CHECK(codex_agent_model_service_tier_at(context, model, 0u, &returned_tier) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_service_tier_id_copy, context, returned_tier, "fast");
    CHECK(codex_agent_model_has_default_service_tier(context, model, &scalar) == CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 1);
    CHECK_COPY(codex_agent_model_default_service_tier_copy, context, model, "fast");
    codex_agent_service_tier_t *missing_tier = NULL;
    CHECK(codex_agent_model_service_tier_at(context, model, 3u, &missing_tier) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(missing_tier == NULL);

    codex_agent_string_view_t step_one_text = LITERAL_VIEW("first");
    codex_agent_string_view_t step_two_text = LITERAL_VIEW("second");
    codex_agent_plan_step_t *step_one = NULL;
    codex_agent_plan_step_t *step_two = NULL;
    CHECK(codex_agent_plan_step_create(context, &step_one_text, CODEX_AGENT_PLAN_STEP_PENDING, &step_one) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plan_step_create(
              context, &step_two_text, CODEX_AGENT_PLAN_STEP_COMPLETED, &step_two) ==
          CODEX_AGENT_STATUS_OK);
    codex_agent_string_view_t explanation = LITERAL_VIEW("because");
    codex_agent_plan_step_t *steps[] = {step_one, step_two, step_one};
    codex_agent_plan_progress_t *plan_progress = NULL;
    CHECK(codex_agent_plan_progress_create(
              context, 1, &explanation, steps, 3u, &plan_progress) == CODEX_AGENT_STATUS_OK);
    steps[0] = step_two;
    CHECK(codex_agent_plan_step_destroy(context, &step_one) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plan_step_destroy(context, &step_two) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plan_progress_has_explanation(context, plan_progress, &scalar) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 1);
    CHECK_COPY(codex_agent_plan_progress_explanation_copy, context, plan_progress, "because");
    CHECK(codex_agent_plan_progress_steps_count(context, plan_progress, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    codex_agent_plan_step_t *returned_step = NULL;
    CHECK(codex_agent_plan_progress_step_at(context, plan_progress, 0u, &returned_step) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plan_step_text_copy, context, returned_step, "first");

    codex_agent_string_view_t hook_id = LITERAL_VIEW("hook");
    codex_agent_string_view_t event_name = LITERAL_VIEW("event");
    codex_agent_string_view_t handler_type = LITERAL_VIEW("command");
    codex_agent_string_view_t status_message = LITERAL_VIEW("blocked");
    codex_agent_string_view_t details[] = {
        LITERAL_VIEW("detail"),
        LITERAL_VIEW("shared"),
        LITERAL_VIEW("detail"),
    };
    codex_agent_hook_activity_t *hook = NULL;
    CHECK(codex_agent_hook_activity_create(
              context,
              &hook_id,
              &event_name,
              &handler_type,
              CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED,
              1,
              &status_message,
              details,
              3u,
              &hook) == CODEX_AGENT_STATUS_OK);
    details[0] = event_name;
    CHECK_COPY(codex_agent_hook_activity_id_copy, context, hook, "hook");
    CHECK_COPY(codex_agent_hook_activity_event_name_copy, context, hook, "event");
    CHECK_COPY(codex_agent_hook_activity_handler_type_copy, context, hook, "command");
    codex_agent_hook_run_status_t hook_status = INT32_MIN;
    CHECK(codex_agent_hook_activity_status(context, hook, &hook_status) == CODEX_AGENT_STATUS_OK);
    CHECK(hook_status == CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED);
    CHECK(codex_agent_hook_activity_has_status_message(context, hook, &scalar) == CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 1);
    CHECK_COPY(codex_agent_hook_activity_status_message_copy, context, hook, "blocked");
    CHECK(codex_agent_hook_activity_details_count(context, hook, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_hook_activity_detail_copy_at, context, hook, 0u, "detail");
    CHECK_COPY_AT(codex_agent_hook_activity_detail_copy_at, context, hook, 1u, "shared");
    CHECK_COPY_AT(codex_agent_hook_activity_detail_copy_at, context, hook, 2u, "detail");

    codex_agent_string_view_t turn_text = LITERAL_VIEW("text");
    codex_agent_string_view_t commentary = LITERAL_VIEW("commentary");
    codex_agent_string_view_t reasoning = LITERAL_VIEW("reasoning");
    codex_agent_string_view_t plan = LITERAL_VIEW("plan");
    codex_agent_string_view_t shell_output = LITERAL_VIEW("shell");
    codex_agent_hook_activity_t *hooks[] = {hook, hook};
    codex_agent_turn_progress_t *turn = NULL;
    CHECK(codex_agent_turn_progress_create(
              context,
              &turn_text,
              &commentary,
              &reasoning,
              &plan,
              1,
              plan_progress,
              &shell_output,
              1,
              -7,
              1,
              CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES,
              hooks,
              2u,
              1,
              &turn) == CODEX_AGENT_STATUS_OK);
    hooks[0] = NULL;
    CHECK(codex_agent_plan_progress_destroy(context, &plan_progress) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_activity_destroy(context, &hook) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_turn_progress_text_copy, context, turn, "text");
    CHECK_COPY(codex_agent_turn_progress_commentary_copy, context, turn, "commentary");
    CHECK_COPY(codex_agent_turn_progress_reasoning_copy, context, turn, "reasoning");
    CHECK_COPY(codex_agent_turn_progress_plan_copy, context, turn, "plan");
    CHECK(codex_agent_turn_progress_has_plan_progress(context, turn, &scalar) == CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 1);
    codex_agent_plan_progress_t *returned_progress = NULL;
    CHECK(codex_agent_turn_progress_plan_progress(context, turn, &returned_progress) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plan_progress_explanation_copy, context, returned_progress, "because");
    CHECK_COPY(codex_agent_turn_progress_shell_output_copy, context, turn, "shell");
    int32_t has_value = INT32_MIN;
    int32_t value = INT32_MIN;
    CHECK(codex_agent_turn_progress_shell_exit_code(context, turn, &has_value, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_value == 1 && value == -7);
    codex_agent_work_activity_t work_activity = INT32_MIN;
    CHECK(codex_agent_turn_progress_work_activity(context, turn, &has_value, &work_activity) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_value == 1 && work_activity == CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES);
    CHECK(codex_agent_turn_progress_hook_activities_count(context, turn, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    codex_agent_hook_activity_t *returned_hook = NULL;
    CHECK(codex_agent_turn_progress_hook_activity_at(context, turn, 1u, &returned_hook) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_hook_activity_id_copy, context, returned_hook, "hook");
    CHECK(codex_agent_turn_progress_is_truncated(context, turn, &scalar) == CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 1);

    codex_agent_string_view_t empty = {NULL, 0u};
    codex_agent_model_t *empty_model = NULL;
    CHECK(codex_agent_model_create(
              context,
              &model_id,
              &model_name,
              &empty,
              NULL,
              0u,
              &empty,
              0,
              NULL,
              0u,
              0,
              &empty,
              &empty_model) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_model_has_default_service_tier(context, empty_model, &scalar) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 0);
    size_t untouched = 71u;
    CHECK(codex_agent_model_default_service_tier_copy(context, empty_model, NULL, 0u, &untouched) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(untouched == 71u);
    codex_agent_plan_progress_t *empty_plan = NULL;
    CHECK(codex_agent_plan_progress_create(context, 0, &empty, NULL, 0u, &empty_plan) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plan_progress_has_explanation(context, empty_plan, &scalar) == CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 0);
    codex_agent_hook_activity_t *empty_hook = NULL;
    CHECK(codex_agent_hook_activity_create(
              context,
              &hook_id,
              &event_name,
              &handler_type,
              CODEX_AGENT_HOOK_RUN_STATUS_RUNNING,
              0,
              &empty,
              NULL,
              0u,
              &empty_hook) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_activity_has_status_message(context, empty_hook, &scalar) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(scalar == 0);
    codex_agent_turn_progress_t *empty_turn = NULL;
    CHECK(codex_agent_turn_progress_create(
              context,
              &empty,
              &empty,
              &empty,
              &empty,
              0,
              NULL,
              &empty,
              0,
              0,
              0,
              0,
              NULL,
              0u,
              0,
              &empty_turn) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_turn_progress_shell_exit_code(context, empty_turn, &has_value, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_value == 0 && value == 0);
    CHECK(codex_agent_turn_progress_work_activity(context, empty_turn, &has_value, &work_activity) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_value == 0 && work_activity == CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND);

    CHECK(codex_agent_turn_progress_destroy(context, &turn) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plan_progress_explanation_copy, context, returned_progress, "because");
    CHECK_COPY(codex_agent_hook_activity_id_copy, context, returned_hook, "hook");
    CHECK(codex_agent_plan_progress_destroy(context, &returned_progress) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_activity_destroy(context, &returned_hook) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plan_step_destroy(context, &returned_step) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_service_tier_destroy(context, &returned_tier) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_model_destroy(context, &model) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_model_destroy(context, &model) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_model_destroy(context, &empty_model) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plan_progress_destroy(context, &empty_plan) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_activity_destroy(context, &empty_hook) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_turn_progress_destroy(context, &empty_turn) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
