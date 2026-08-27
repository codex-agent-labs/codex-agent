import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class DesktopCAbiExportPolicyTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("gradle/build-logic").isDirectory }

    @Test
    fun `all native C ABI targets have exact export and loader policy`() {
        val abi10 = listOf(
            "codex_agent_abi_is_compatible",
            "codex_agent_abi_version",
            "codex_agent_context_create",
            "codex_agent_context_destroy",
        )
        val abi11 = listOf(
            "codex_agent_active_conversation",
            "codex_agent_agent_conversations",
            "codex_agent_agent_release",
            "codex_agent_agent_retain",
            "codex_agent_conversation_cancel_turn",
            "codex_agent_conversation_close",
            "codex_agent_conversation_is_same",
            "codex_agent_conversation_release",
            "codex_agent_conversation_retain",
            "codex_agent_conversation_send",
            "codex_agent_conversation_state_failure",
            "codex_agent_conversation_state_get",
            "codex_agent_conversation_state_status",
            "codex_agent_conversation_state_subscribe",
            "codex_agent_conversations_active_get",
            "codex_agent_conversations_active_subscribe",
            "codex_agent_conversations_open",
            "codex_agent_conversations_release",
            "codex_agent_conversations_retain",
            "codex_agent_failure_code_copy",
            "codex_agent_failure_is_recoverable",
            "codex_agent_failure_message_copy",
            "codex_agent_failure_release",
            "codex_agent_failure_retain",
            "codex_agent_host_close",
            "codex_agent_host_create",
            "codex_agent_host_release",
            "codex_agent_host_retain",
            "codex_agent_host_select_workspace",
            "codex_agent_host_state_agent",
            "codex_agent_host_state_failure",
            "codex_agent_host_state_get",
            "codex_agent_host_state_has_workspace",
            "codex_agent_host_state_kind",
            "codex_agent_host_state_requirement_message_copy",
            "codex_agent_host_state_requirement_reason",
            "codex_agent_host_state_subscribe",
            "codex_agent_host_state_workspace_display_name_copy",
            "codex_agent_host_state_workspace_path_copy",
            "codex_agent_operation_cancel",
            "codex_agent_operation_conversation",
            "codex_agent_operation_destroy",
            "codex_agent_operation_failure",
            "codex_agent_operation_result",
            "codex_agent_snapshot_destroy",
            "codex_agent_subscription_destroy",
        )
        val abi12 = listOf(
            "codex_agent_approval_preset_display_name_copy",
            "codex_agent_capability_display_label_copy",
            "codex_agent_capability_has_icon",
            "codex_agent_capability_icon_copy",
            "codex_agent_capability_id_copy",
            "codex_agent_capability_prompt_label_copy",
            "codex_agent_conversation_id_create",
            "codex_agent_conversation_id_destroy",
            "codex_agent_conversation_id_value_copy",
            "codex_agent_conversation_summary_conversation_id",
            "codex_agent_conversation_summary_create",
            "codex_agent_conversation_summary_destroy",
            "codex_agent_conversation_summary_title_copy",
            "codex_agent_conversation_summary_updated_at_epoch_seconds",
            "codex_agent_elicitation_validation_issue_create",
            "codex_agent_elicitation_validation_issue_destroy",
            "codex_agent_elicitation_validation_issue_field_name_copy",
            "codex_agent_elicitation_validation_issue_reason",
            "codex_agent_failure_create",
            "codex_agent_form_option_create",
            "codex_agent_form_option_description_copy",
            "codex_agent_form_option_destroy",
            "codex_agent_form_option_has_description",
            "codex_agent_form_option_title_copy",
            "codex_agent_form_option_value_copy",
            "codex_agent_mcp_environment_variable_create",
            "codex_agent_mcp_environment_variable_destroy",
            "codex_agent_mcp_environment_variable_name_copy",
            "codex_agent_mcp_environment_variable_source",
            "codex_agent_mcp_oauth_configuration_callback_port",
            "codex_agent_mcp_oauth_configuration_client_id_copy",
            "codex_agent_mcp_oauth_configuration_create",
            "codex_agent_mcp_oauth_configuration_destroy",
            "codex_agent_mcp_oauth_configuration_has_client_id",
            "codex_agent_mcp_tool_configuration_approval",
            "codex_agent_mcp_tool_configuration_create",
            "codex_agent_mcp_tool_configuration_destroy",
            "codex_agent_plan_step_create",
            "codex_agent_plan_step_destroy",
            "codex_agent_plan_step_status",
            "codex_agent_plan_step_text_copy",
            "codex_agent_plugin_reference_create",
            "codex_agent_plugin_reference_destroy",
            "codex_agent_plugin_reference_has_marketplace_path",
            "codex_agent_plugin_reference_has_remote_plugin_id",
            "codex_agent_plugin_reference_id_copy",
            "codex_agent_plugin_reference_marketplace_name_copy",
            "codex_agent_plugin_reference_marketplace_path_copy",
            "codex_agent_plugin_reference_name_copy",
            "codex_agent_plugin_reference_remote_plugin_id_copy",
            "codex_agent_plugin_reference_uri_copy",
            "codex_agent_plugin_skill_create",
            "codex_agent_plugin_skill_description_copy",
            "codex_agent_plugin_skill_destroy",
            "codex_agent_plugin_skill_has_path",
            "codex_agent_plugin_skill_is_enabled",
            "codex_agent_plugin_skill_name_copy",
            "codex_agent_plugin_skill_path_copy",
            "codex_agent_service_tier_create",
            "codex_agent_service_tier_description_copy",
            "codex_agent_service_tier_destroy",
            "codex_agent_service_tier_id_copy",
            "codex_agent_service_tier_name_copy",
            "codex_agent_skill_chunk_content_copy",
            "codex_agent_skill_chunk_create",
            "codex_agent_skill_chunk_destroy",
            "codex_agent_skill_chunk_next_offset",
            "codex_agent_skill_chunk_total_bytes",
            "codex_agent_skill_scope_display_name_copy",
            "codex_agent_workspace_create",
            "codex_agent_workspace_destroy",
            "codex_agent_workspace_display_name_copy",
            "codex_agent_workspace_path_copy",
            "codex_agent_workspace_resolution_available_create",
            "codex_agent_workspace_resolution_available_destroy",
            "codex_agent_workspace_resolution_available_workspace",
            "codex_agent_workspace_selection_required_create",
            "codex_agent_workspace_selection_required_destroy",
            "codex_agent_workspace_selection_required_message_copy",
            "codex_agent_workspace_selection_required_reason",
        )
        val exports = repository.resolve("codex-agent-runtime-desktop/native/c-api/exports")
        val all = (abi10 + abi11 + abi12).sorted()
        assertEquals(
            all.map { "_$it" },
            exports.resolve("macos.exports").readLines(),
        )
        assertEquals(
            linuxVersion("1.0", abi10) + "\n" +
                linuxVersion("1.1", abi11, "CODEX_AGENT_1.0") + "\n" +
                linuxVersion("1.2", abi12, "CODEX_AGENT_1.1"),
            exports.resolve("linux.map").readText(),
        )
        assertEquals(
            "LIBRARY codex_agent.dll\nEXPORTS\n" +
                all.joinToString("\n", postfix = "\n") { "    $it" },
            exports.resolve("windows.def").readText(),
        )

        val plugin = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
        ).readText()
        listOf(
            "target.name.startsWith(\"macos\")",
            "-Wl,-exported_symbols_list,",
            "-Wl,-install_name,@rpath/libcodex_agent.dylib",
            "-Wl,-compatibility_version,1.0.0",
            "-Wl,-current_version,1.2.0",
            "target.name.startsWith(\"linux\")",
            "-Wl,--version-script,",
            "-Wl,-soname,libcodex_agent.so.1",
            "target.name == \"mingwX64\"",
            "-Wl,--exclude-all-symbols",
            "native/c-api/exports/windows.def",
            "linkTaskProvider.configure",
            "inputs.file(exportPolicyFile)",
            ".withPropertyName(\"codexAgentCAbiExportPolicy\")",
            ".withPathSensitivity(PathSensitivity.RELATIVE)",
        ).forEach { expected ->
            assertTrue(expected in plugin, expected)
        }
    }

    private fun linuxVersion(version: String, symbols: List<String>, parent: String? = null): String =
        buildString {
            append("CODEX_AGENT_").append(version).append(" {\n    global:\n")
            symbols.forEach { append("        ").append(it).append(";\n") }
            if (parent != null) append("    local:\n        *;\n")
            append("}")
            if (parent != null) append(" ").append(parent)
            append(";\n")
        }
}
