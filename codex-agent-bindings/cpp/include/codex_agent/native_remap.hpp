#pragma once

#ifndef CODEX_AGENT_CPP_STATIC_TEST_DISPATCH
#define codex_agent_abi_is_compatible \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_abi_is_compatible), \
        ::codex_agent::detail::NativeSymbol::s000>::call
#define codex_agent_active_conversation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_active_conversation), \
        ::codex_agent::detail::NativeSymbol::s001>::call
#define codex_agent_agent_authentication \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_authentication), \
        ::codex_agent::detail::NativeSymbol::s002>::call
#define codex_agent_agent_connectors \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_connectors), \
        ::codex_agent::detail::NativeSymbol::s003>::call
#define codex_agent_agent_conversations \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_conversations), \
        ::codex_agent::detail::NativeSymbol::s004>::call
#define codex_agent_agent_hooks \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_hooks), \
        ::codex_agent::detail::NativeSymbol::s005>::call
#define codex_agent_agent_integration_authorization \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_integration_authorization), \
        ::codex_agent::detail::NativeSymbol::s006>::call
#define codex_agent_agent_interactions \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_interactions), \
        ::codex_agent::detail::NativeSymbol::s007>::call
#define codex_agent_agent_mcp_servers \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_mcp_servers), \
        ::codex_agent::detail::NativeSymbol::s008>::call
#define codex_agent_agent_models \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_models), \
        ::codex_agent::detail::NativeSymbol::s009>::call
#define codex_agent_agent_plugins \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_plugins), \
        ::codex_agent::detail::NativeSymbol::s010>::call
#define codex_agent_agent_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_release), \
        ::codex_agent::detail::NativeSymbol::s011>::call
#define codex_agent_agent_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_retain), \
        ::codex_agent::detail::NativeSymbol::s012>::call
#define codex_agent_agent_skills \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_skills), \
        ::codex_agent::detail::NativeSymbol::s013>::call
#define codex_agent_agent_workspace \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_agent_workspace), \
        ::codex_agent::detail::NativeSymbol::s014>::call
#define codex_agent_authentication_authenticate_api_key \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_authenticate_api_key), \
        ::codex_agent::detail::NativeSymbol::s015>::call
#define codex_agent_authentication_authenticate_chat_gpt_browser \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_authenticate_chat_gpt_browser), \
        ::codex_agent::detail::NativeSymbol::s016>::call
#define codex_agent_authentication_authenticate_chat_gpt_device_code \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_authenticate_chat_gpt_device_code), \
        ::codex_agent::detail::NativeSymbol::s017>::call
#define codex_agent_authentication_cancel \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_cancel), \
        ::codex_agent::detail::NativeSymbol::s018>::call
#define codex_agent_authentication_is_authenticated_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_is_authenticated_get), \
        ::codex_agent::detail::NativeSymbol::s019>::call
#define codex_agent_authentication_is_authenticated_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_is_authenticated_subscribe), \
        ::codex_agent::detail::NativeSymbol::s020>::call
#define codex_agent_authentication_is_authenticating_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_is_authenticating_get), \
        ::codex_agent::detail::NativeSymbol::s021>::call
#define codex_agent_authentication_is_authenticating_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_is_authenticating_subscribe), \
        ::codex_agent::detail::NativeSymbol::s022>::call
#define codex_agent_authentication_method_api_key_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_method_api_key_create), \
        ::codex_agent::detail::NativeSymbol::s023>::call
#define codex_agent_authentication_method_api_key_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_method_api_key_destroy), \
        ::codex_agent::detail::NativeSymbol::s024>::call
#define codex_agent_authentication_method_chat_gpt_browser_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_method_chat_gpt_browser_create), \
        ::codex_agent::detail::NativeSymbol::s025>::call
#define codex_agent_authentication_method_chat_gpt_browser_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_method_chat_gpt_browser_destroy), \
        ::codex_agent::detail::NativeSymbol::s026>::call
#define codex_agent_authentication_method_chat_gpt_device_code_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_method_chat_gpt_device_code_create), \
        ::codex_agent::detail::NativeSymbol::s027>::call
#define codex_agent_authentication_method_chat_gpt_device_code_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_method_chat_gpt_device_code_destroy), \
        ::codex_agent::detail::NativeSymbol::s028>::call
#define codex_agent_authentication_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_release), \
        ::codex_agent::detail::NativeSymbol::s029>::call
#define codex_agent_authentication_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_retain), \
        ::codex_agent::detail::NativeSymbol::s030>::call
#define codex_agent_authentication_sign_out \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_sign_out), \
        ::codex_agent::detail::NativeSymbol::s031>::call
#define codex_agent_authentication_state_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_destroy), \
        ::codex_agent::detail::NativeSymbol::s032>::call
#define codex_agent_authentication_state_device_user_code_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_device_user_code_copy), \
        ::codex_agent::detail::NativeSymbol::s033>::call
#define codex_agent_authentication_state_device_verification_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_device_verification_url), \
        ::codex_agent::detail::NativeSymbol::s034>::call
#define codex_agent_authentication_state_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_failure), \
        ::codex_agent::detail::NativeSymbol::s035>::call
#define codex_agent_authentication_state_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_get), \
        ::codex_agent::detail::NativeSymbol::s036>::call
#define codex_agent_authentication_state_has_device_user_code \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_has_device_user_code), \
        ::codex_agent::detail::NativeSymbol::s037>::call
#define codex_agent_authentication_state_has_device_verification_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_has_device_verification_url), \
        ::codex_agent::detail::NativeSymbol::s038>::call
#define codex_agent_authentication_state_has_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_has_failure), \
        ::codex_agent::detail::NativeSymbol::s039>::call
#define codex_agent_authentication_state_has_pending_sign_in_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_has_pending_sign_in_url), \
        ::codex_agent::detail::NativeSymbol::s040>::call
#define codex_agent_authentication_state_pending_sign_in_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_pending_sign_in_url), \
        ::codex_agent::detail::NativeSymbol::s041>::call
#define codex_agent_authentication_state_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_status), \
        ::codex_agent::detail::NativeSymbol::s042>::call
#define codex_agent_authentication_state_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_subscribe), \
        ::codex_agent::detail::NativeSymbol::s043>::call
#define codex_agent_authentication_state_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authentication_state_value), \
        ::codex_agent::detail::NativeSymbol::s044>::call
#define codex_agent_authorization_url_chat_gpt \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authorization_url_chat_gpt), \
        ::codex_agent::detail::NativeSymbol::s045>::call
#define codex_agent_authorization_url_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authorization_url_destroy), \
        ::codex_agent::detail::NativeSymbol::s046>::call
#define codex_agent_authorization_url_external \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authorization_url_external), \
        ::codex_agent::detail::NativeSymbol::s047>::call
#define codex_agent_authorization_url_purpose \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authorization_url_purpose), \
        ::codex_agent::detail::NativeSymbol::s048>::call
#define codex_agent_authorization_url_value_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_authorization_url_value_copy), \
        ::codex_agent::detail::NativeSymbol::s049>::call
#define codex_agent_connector_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_create), \
        ::codex_agent::detail::NativeSymbol::s050>::call
#define codex_agent_connector_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_description_copy), \
        ::codex_agent::detail::NativeSymbol::s051>::call
#define codex_agent_connector_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_destroy), \
        ::codex_agent::detail::NativeSymbol::s052>::call
#define codex_agent_connector_has_install_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_has_install_url), \
        ::codex_agent::detail::NativeSymbol::s053>::call
#define codex_agent_connector_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_id_copy), \
        ::codex_agent::detail::NativeSymbol::s054>::call
#define codex_agent_connector_install_url_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_install_url_copy), \
        ::codex_agent::detail::NativeSymbol::s055>::call
#define codex_agent_connector_is_accessible \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_is_accessible), \
        ::codex_agent::detail::NativeSymbol::s056>::call
#define codex_agent_connector_is_enabled \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_is_enabled), \
        ::codex_agent::detail::NativeSymbol::s057>::call
#define codex_agent_connector_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_name_copy), \
        ::codex_agent::detail::NativeSymbol::s058>::call
#define codex_agent_connector_plugin_names_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_plugin_names_copy_at), \
        ::codex_agent::detail::NativeSymbol::s059>::call
#define codex_agent_connector_plugin_names_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connector_plugin_names_count), \
        ::codex_agent::detail::NativeSymbol::s060>::call
#define codex_agent_connectors_is_available \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connectors_is_available), \
        ::codex_agent::detail::NativeSymbol::s061>::call
#define codex_agent_connectors_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connectors_list), \
        ::codex_agent::detail::NativeSymbol::s062>::call
#define codex_agent_connectors_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connectors_release), \
        ::codex_agent::detail::NativeSymbol::s063>::call
#define codex_agent_connectors_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_connectors_retain), \
        ::codex_agent::detail::NativeSymbol::s064>::call
#define codex_agent_context_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_context_create), \
        ::codex_agent::detail::NativeSymbol::s065>::call
#define codex_agent_context_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_context_destroy), \
        ::codex_agent::detail::NativeSymbol::s066>::call
#define codex_agent_conversation_active_turn_progress_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_active_turn_progress_get), \
        ::codex_agent::detail::NativeSymbol::s067>::call
#define codex_agent_conversation_active_turn_progress_has_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_active_turn_progress_has_value), \
        ::codex_agent::detail::NativeSymbol::s068>::call
#define codex_agent_conversation_active_turn_progress_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_active_turn_progress_subscribe), \
        ::codex_agent::detail::NativeSymbol::s069>::call
#define codex_agent_conversation_active_turn_progress_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_active_turn_progress_value), \
        ::codex_agent::detail::NativeSymbol::s070>::call
#define codex_agent_conversation_can_cancel_turn_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_cancel_turn_get), \
        ::codex_agent::detail::NativeSymbol::s071>::call
#define codex_agent_conversation_can_cancel_turn_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_cancel_turn_subscribe), \
        ::codex_agent::detail::NativeSymbol::s072>::call
#define codex_agent_conversation_can_reload_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_reload_get), \
        ::codex_agent::detail::NativeSymbol::s073>::call
#define codex_agent_conversation_can_reload_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_reload_subscribe), \
        ::codex_agent::detail::NativeSymbol::s074>::call
#define codex_agent_conversation_can_run_shell_command_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_run_shell_command_get), \
        ::codex_agent::detail::NativeSymbol::s075>::call
#define codex_agent_conversation_can_run_shell_command_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_run_shell_command_subscribe), \
        ::codex_agent::detail::NativeSymbol::s076>::call
#define codex_agent_conversation_can_start_turn_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_start_turn_get), \
        ::codex_agent::detail::NativeSymbol::s077>::call
#define codex_agent_conversation_can_start_turn_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_can_start_turn_subscribe), \
        ::codex_agent::detail::NativeSymbol::s078>::call
#define codex_agent_conversation_cancel_turn \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_cancel_turn), \
        ::codex_agent::detail::NativeSymbol::s079>::call
#define codex_agent_conversation_close \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_close), \
        ::codex_agent::detail::NativeSymbol::s080>::call
#define codex_agent_conversation_current_messages_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_current_messages_at), \
        ::codex_agent::detail::NativeSymbol::s081>::call
#define codex_agent_conversation_current_messages_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_current_messages_count), \
        ::codex_agent::detail::NativeSymbol::s082>::call
#define codex_agent_conversation_current_messages_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_current_messages_get), \
        ::codex_agent::detail::NativeSymbol::s083>::call
#define codex_agent_conversation_current_messages_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_current_messages_subscribe), \
        ::codex_agent::detail::NativeSymbol::s084>::call
#define codex_agent_conversation_id_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_id_create), \
        ::codex_agent::detail::NativeSymbol::s085>::call
#define codex_agent_conversation_id_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_id_destroy), \
        ::codex_agent::detail::NativeSymbol::s086>::call
#define codex_agent_conversation_id_value_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_id_value_copy), \
        ::codex_agent::detail::NativeSymbol::s087>::call
#define codex_agent_conversation_is_same \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_is_same), \
        ::codex_agent::detail::NativeSymbol::s088>::call
#define codex_agent_conversation_is_turn_active_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_is_turn_active_get), \
        ::codex_agent::detail::NativeSymbol::s089>::call
#define codex_agent_conversation_is_turn_active_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_is_turn_active_subscribe), \
        ::codex_agent::detail::NativeSymbol::s090>::call
#define codex_agent_conversation_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_release), \
        ::codex_agent::detail::NativeSymbol::s091>::call
#define codex_agent_conversation_reload \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_reload), \
        ::codex_agent::detail::NativeSymbol::s092>::call
#define codex_agent_conversation_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_retain), \
        ::codex_agent::detail::NativeSymbol::s093>::call
#define codex_agent_conversation_run_shell_command \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_run_shell_command), \
        ::codex_agent::detail::NativeSymbol::s094>::call
#define codex_agent_conversation_send \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_send), \
        ::codex_agent::detail::NativeSymbol::s095>::call
#define codex_agent_conversation_send_request \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_send_request), \
        ::codex_agent::detail::NativeSymbol::s096>::call
#define codex_agent_conversation_state_can_cancel_turn \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_can_cancel_turn), \
        ::codex_agent::detail::NativeSymbol::s097>::call
#define codex_agent_conversation_state_can_reload \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_can_reload), \
        ::codex_agent::detail::NativeSymbol::s098>::call
#define codex_agent_conversation_state_can_start_turn \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_can_start_turn), \
        ::codex_agent::detail::NativeSymbol::s099>::call
#define codex_agent_conversation_state_conversation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_conversation), \
        ::codex_agent::detail::NativeSymbol::s100>::call
#define codex_agent_conversation_state_conversation_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_conversation_id), \
        ::codex_agent::detail::NativeSymbol::s101>::call
#define codex_agent_conversation_state_effort_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_effort_copy), \
        ::codex_agent::detail::NativeSymbol::s102>::call
#define codex_agent_conversation_state_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_failure), \
        ::codex_agent::detail::NativeSymbol::s103>::call
#define codex_agent_conversation_state_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_get), \
        ::codex_agent::detail::NativeSymbol::s104>::call
#define codex_agent_conversation_state_has_conversation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_has_conversation), \
        ::codex_agent::detail::NativeSymbol::s105>::call
#define codex_agent_conversation_state_has_conversation_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_has_conversation_id), \
        ::codex_agent::detail::NativeSymbol::s106>::call
#define codex_agent_conversation_state_has_effort \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_has_effort), \
        ::codex_agent::detail::NativeSymbol::s107>::call
#define codex_agent_conversation_state_has_model \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_has_model), \
        ::codex_agent::detail::NativeSymbol::s108>::call
#define codex_agent_conversation_state_has_service_tier \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_has_service_tier), \
        ::codex_agent::detail::NativeSymbol::s109>::call
#define codex_agent_conversation_state_model_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_model_copy), \
        ::codex_agent::detail::NativeSymbol::s110>::call
#define codex_agent_conversation_state_service_tier_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_service_tier_copy), \
        ::codex_agent::detail::NativeSymbol::s111>::call
#define codex_agent_conversation_state_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_status), \
        ::codex_agent::detail::NativeSymbol::s112>::call
#define codex_agent_conversation_state_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_subscribe), \
        ::codex_agent::detail::NativeSymbol::s113>::call
#define codex_agent_conversation_state_turn_progress \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_state_turn_progress), \
        ::codex_agent::detail::NativeSymbol::s114>::call
#define codex_agent_conversation_summary_conversation_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_summary_conversation_id), \
        ::codex_agent::detail::NativeSymbol::s115>::call
#define codex_agent_conversation_summary_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_summary_destroy), \
        ::codex_agent::detail::NativeSymbol::s116>::call
#define codex_agent_conversation_summary_title_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_summary_title_copy), \
        ::codex_agent::detail::NativeSymbol::s117>::call
#define codex_agent_conversation_summary_updated_at_epoch_seconds \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_summary_updated_at_epoch_seconds), \
        ::codex_agent::detail::NativeSymbol::s118>::call
#define codex_agent_conversation_value_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_value_destroy), \
        ::codex_agent::detail::NativeSymbol::s119>::call
#define codex_agent_conversation_value_message_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_value_message_at), \
        ::codex_agent::detail::NativeSymbol::s120>::call
#define codex_agent_conversation_value_messages_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_value_messages_count), \
        ::codex_agent::detail::NativeSymbol::s121>::call
#define codex_agent_conversation_value_summary \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversation_value_summary), \
        ::codex_agent::detail::NativeSymbol::s122>::call
#define codex_agent_conversations_active_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_active_get), \
        ::codex_agent::detail::NativeSymbol::s123>::call
#define codex_agent_conversations_active_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_active_subscribe), \
        ::codex_agent::detail::NativeSymbol::s124>::call
#define codex_agent_conversations_delete \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_delete), \
        ::codex_agent::detail::NativeSymbol::s125>::call
#define codex_agent_conversations_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_list), \
        ::codex_agent::detail::NativeSymbol::s126>::call
#define codex_agent_conversations_open \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_open), \
        ::codex_agent::detail::NativeSymbol::s127>::call
#define codex_agent_conversations_read \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_read), \
        ::codex_agent::detail::NativeSymbol::s128>::call
#define codex_agent_conversations_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_release), \
        ::codex_agent::detail::NativeSymbol::s129>::call
#define codex_agent_conversations_rename \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_rename), \
        ::codex_agent::detail::NativeSymbol::s130>::call
#define codex_agent_conversations_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_conversations_retain), \
        ::codex_agent::detail::NativeSymbol::s131>::call
#define codex_agent_elicitation_accept \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_accept), \
        ::codex_agent::detail::NativeSymbol::s132>::call
#define codex_agent_elicitation_accepts \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_accepts), \
        ::codex_agent::detail::NativeSymbol::s133>::call
#define codex_agent_elicitation_conversation_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_conversation_id), \
        ::codex_agent::detail::NativeSymbol::s134>::call
#define codex_agent_elicitation_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_create), \
        ::codex_agent::detail::NativeSymbol::s135>::call
#define codex_agent_elicitation_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_destroy), \
        ::codex_agent::detail::NativeSymbol::s136>::call
#define codex_agent_elicitation_form_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_form_at), \
        ::codex_agent::detail::NativeSymbol::s137>::call
#define codex_agent_elicitation_form_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_form_count), \
        ::codex_agent::detail::NativeSymbol::s138>::call
#define codex_agent_elicitation_has_form \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_has_form), \
        ::codex_agent::detail::NativeSymbol::s139>::call
#define codex_agent_elicitation_has_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_has_url), \
        ::codex_agent::detail::NativeSymbol::s140>::call
#define codex_agent_elicitation_initial_values \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_initial_values), \
        ::codex_agent::detail::NativeSymbol::s141>::call
#define codex_agent_elicitation_message_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_message_copy), \
        ::codex_agent::detail::NativeSymbol::s142>::call
#define codex_agent_elicitation_request_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_request_id_copy), \
        ::codex_agent::detail::NativeSymbol::s143>::call
#define codex_agent_elicitation_response_action \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_action), \
        ::codex_agent::detail::NativeSymbol::s144>::call
#define codex_agent_elicitation_response_cancel \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_cancel), \
        ::codex_agent::detail::NativeSymbol::s145>::call
#define codex_agent_elicitation_response_content_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_content_count), \
        ::codex_agent::detail::NativeSymbol::s146>::call
#define codex_agent_elicitation_response_content_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_content_value), \
        ::codex_agent::detail::NativeSymbol::s147>::call
#define codex_agent_elicitation_response_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_create), \
        ::codex_agent::detail::NativeSymbol::s148>::call
#define codex_agent_elicitation_response_decline \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_decline), \
        ::codex_agent::detail::NativeSymbol::s149>::call
#define codex_agent_elicitation_response_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_response_destroy), \
        ::codex_agent::detail::NativeSymbol::s150>::call
#define codex_agent_elicitation_server_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_server_name_copy), \
        ::codex_agent::detail::NativeSymbol::s151>::call
#define codex_agent_elicitation_url_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_url_copy), \
        ::codex_agent::detail::NativeSymbol::s152>::call
#define codex_agent_elicitation_validate \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validate), \
        ::codex_agent::detail::NativeSymbol::s153>::call
#define codex_agent_elicitation_validation_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validation_destroy), \
        ::codex_agent::detail::NativeSymbol::s154>::call
#define codex_agent_elicitation_validation_issue_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validation_issue_at), \
        ::codex_agent::detail::NativeSymbol::s155>::call
#define codex_agent_elicitation_validation_issue_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validation_issue_count), \
        ::codex_agent::detail::NativeSymbol::s156>::call
#define codex_agent_elicitation_validation_issue_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validation_issue_destroy), \
        ::codex_agent::detail::NativeSymbol::s157>::call
#define codex_agent_elicitation_validation_issue_field_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validation_issue_field_name_copy), \
        ::codex_agent::detail::NativeSymbol::s158>::call
#define codex_agent_elicitation_validation_issue_reason \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_elicitation_validation_issue_reason), \
        ::codex_agent::detail::NativeSymbol::s159>::call
#define codex_agent_failure_code_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_failure_code_copy), \
        ::codex_agent::detail::NativeSymbol::s160>::call
#define codex_agent_failure_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_failure_create), \
        ::codex_agent::detail::NativeSymbol::s161>::call
#define codex_agent_failure_is_recoverable \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_failure_is_recoverable), \
        ::codex_agent::detail::NativeSymbol::s162>::call
#define codex_agent_failure_message_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_failure_message_copy), \
        ::codex_agent::detail::NativeSymbol::s163>::call
#define codex_agent_failure_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_failure_release), \
        ::codex_agent::detail::NativeSymbol::s164>::call
#define codex_agent_form_boolean_value_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_boolean_value_create), \
        ::codex_agent::detail::NativeSymbol::s165>::call
#define codex_agent_form_boolean_value_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_boolean_value_destroy), \
        ::codex_agent::detail::NativeSymbol::s166>::call
#define codex_agent_form_boolean_value_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_boolean_value_value), \
        ::codex_agent::detail::NativeSymbol::s167>::call
#define codex_agent_form_content_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_content_count), \
        ::codex_agent::detail::NativeSymbol::s168>::call
#define codex_agent_form_content_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_content_create), \
        ::codex_agent::detail::NativeSymbol::s169>::call
#define codex_agent_form_content_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_content_destroy), \
        ::codex_agent::detail::NativeSymbol::s170>::call
#define codex_agent_form_content_key_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_content_key_copy), \
        ::codex_agent::detail::NativeSymbol::s171>::call
#define codex_agent_form_content_value_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_content_value_at), \
        ::codex_agent::detail::NativeSymbol::s172>::call
#define codex_agent_form_field_accepts \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_accepts), \
        ::codex_agent::detail::NativeSymbol::s173>::call
#define codex_agent_form_field_allows_other \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_allows_other), \
        ::codex_agent::detail::NativeSymbol::s174>::call
#define codex_agent_form_field_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_create), \
        ::codex_agent::detail::NativeSymbol::s175>::call
#define codex_agent_form_field_default_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_default_value), \
        ::codex_agent::detail::NativeSymbol::s176>::call
#define codex_agent_form_field_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_description_copy), \
        ::codex_agent::detail::NativeSymbol::s177>::call
#define codex_agent_form_field_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_destroy), \
        ::codex_agent::detail::NativeSymbol::s178>::call
#define codex_agent_form_field_format \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_format), \
        ::codex_agent::detail::NativeSymbol::s179>::call
#define codex_agent_form_field_has_default_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_has_default_value), \
        ::codex_agent::detail::NativeSymbol::s180>::call
#define codex_agent_form_field_has_description \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_has_description), \
        ::codex_agent::detail::NativeSymbol::s181>::call
#define codex_agent_form_field_is_required \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_is_required), \
        ::codex_agent::detail::NativeSymbol::s182>::call
#define codex_agent_form_field_is_secret \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_is_secret), \
        ::codex_agent::detail::NativeSymbol::s183>::call
#define codex_agent_form_field_maximum \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_maximum), \
        ::codex_agent::detail::NativeSymbol::s184>::call
#define codex_agent_form_field_maximum_length \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_maximum_length), \
        ::codex_agent::detail::NativeSymbol::s185>::call
#define codex_agent_form_field_maximum_selections \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_maximum_selections), \
        ::codex_agent::detail::NativeSymbol::s186>::call
#define codex_agent_form_field_minimum \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_minimum), \
        ::codex_agent::detail::NativeSymbol::s187>::call
#define codex_agent_form_field_minimum_length \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_minimum_length), \
        ::codex_agent::detail::NativeSymbol::s188>::call
#define codex_agent_form_field_minimum_selections \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_minimum_selections), \
        ::codex_agent::detail::NativeSymbol::s189>::call
#define codex_agent_form_field_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_name_copy), \
        ::codex_agent::detail::NativeSymbol::s190>::call
#define codex_agent_form_field_option_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_option_at), \
        ::codex_agent::detail::NativeSymbol::s191>::call
#define codex_agent_form_field_options_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_options_count), \
        ::codex_agent::detail::NativeSymbol::s192>::call
#define codex_agent_form_field_title_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_title_copy), \
        ::codex_agent::detail::NativeSymbol::s193>::call
#define codex_agent_form_field_type \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_field_type), \
        ::codex_agent::detail::NativeSymbol::s194>::call
#define codex_agent_form_number_value_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_number_value_create), \
        ::codex_agent::detail::NativeSymbol::s195>::call
#define codex_agent_form_number_value_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_number_value_destroy), \
        ::codex_agent::detail::NativeSymbol::s196>::call
#define codex_agent_form_number_value_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_number_value_value), \
        ::codex_agent::detail::NativeSymbol::s197>::call
#define codex_agent_form_option_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_option_create), \
        ::codex_agent::detail::NativeSymbol::s198>::call
#define codex_agent_form_option_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_option_description_copy), \
        ::codex_agent::detail::NativeSymbol::s199>::call
#define codex_agent_form_option_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_option_destroy), \
        ::codex_agent::detail::NativeSymbol::s200>::call
#define codex_agent_form_option_has_description \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_option_has_description), \
        ::codex_agent::detail::NativeSymbol::s201>::call
#define codex_agent_form_option_title_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_option_title_copy), \
        ::codex_agent::detail::NativeSymbol::s202>::call
#define codex_agent_form_option_value_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_option_value_copy), \
        ::codex_agent::detail::NativeSymbol::s203>::call
#define codex_agent_form_text_list_value_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_list_value_copy_at), \
        ::codex_agent::detail::NativeSymbol::s204>::call
#define codex_agent_form_text_list_value_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_list_value_count), \
        ::codex_agent::detail::NativeSymbol::s205>::call
#define codex_agent_form_text_list_value_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_list_value_create), \
        ::codex_agent::detail::NativeSymbol::s206>::call
#define codex_agent_form_text_list_value_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_list_value_destroy), \
        ::codex_agent::detail::NativeSymbol::s207>::call
#define codex_agent_form_text_value_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_value_create), \
        ::codex_agent::detail::NativeSymbol::s208>::call
#define codex_agent_form_text_value_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_value_destroy), \
        ::codex_agent::detail::NativeSymbol::s209>::call
#define codex_agent_form_text_value_value_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_text_value_value_copy), \
        ::codex_agent::detail::NativeSymbol::s210>::call
#define codex_agent_form_value_boolean \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_boolean), \
        ::codex_agent::detail::NativeSymbol::s211>::call
#define codex_agent_form_value_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_destroy), \
        ::codex_agent::detail::NativeSymbol::s212>::call
#define codex_agent_form_value_from_boolean \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_from_boolean), \
        ::codex_agent::detail::NativeSymbol::s213>::call
#define codex_agent_form_value_from_number \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_from_number), \
        ::codex_agent::detail::NativeSymbol::s214>::call
#define codex_agent_form_value_from_text \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_from_text), \
        ::codex_agent::detail::NativeSymbol::s215>::call
#define codex_agent_form_value_from_text_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_from_text_list), \
        ::codex_agent::detail::NativeSymbol::s216>::call
#define codex_agent_form_value_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_kind), \
        ::codex_agent::detail::NativeSymbol::s217>::call
#define codex_agent_form_value_number \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_number), \
        ::codex_agent::detail::NativeSymbol::s218>::call
#define codex_agent_form_value_text \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_text), \
        ::codex_agent::detail::NativeSymbol::s219>::call
#define codex_agent_form_value_text_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_form_value_text_list), \
        ::codex_agent::detail::NativeSymbol::s220>::call
#define codex_agent_hook_activity_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_destroy), \
        ::codex_agent::detail::NativeSymbol::s221>::call
#define codex_agent_hook_activity_detail_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_detail_copy_at), \
        ::codex_agent::detail::NativeSymbol::s222>::call
#define codex_agent_hook_activity_details_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_details_count), \
        ::codex_agent::detail::NativeSymbol::s223>::call
#define codex_agent_hook_activity_event_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_event_name_copy), \
        ::codex_agent::detail::NativeSymbol::s224>::call
#define codex_agent_hook_activity_handler_type_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_handler_type_copy), \
        ::codex_agent::detail::NativeSymbol::s225>::call
#define codex_agent_hook_activity_has_status_message \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_has_status_message), \
        ::codex_agent::detail::NativeSymbol::s226>::call
#define codex_agent_hook_activity_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_id_copy), \
        ::codex_agent::detail::NativeSymbol::s227>::call
#define codex_agent_hook_activity_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_status), \
        ::codex_agent::detail::NativeSymbol::s228>::call
#define codex_agent_hook_activity_status_message_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_activity_status_message_copy), \
        ::codex_agent::detail::NativeSymbol::s229>::call
#define codex_agent_hook_can_trust \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_can_trust), \
        ::codex_agent::detail::NativeSymbol::s230>::call
#define codex_agent_hook_can_uninstall \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_can_uninstall), \
        ::codex_agent::detail::NativeSymbol::s231>::call
#define codex_agent_hook_catalog_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_destroy), \
        ::codex_agent::detail::NativeSymbol::s232>::call
#define codex_agent_hook_catalog_errors_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_errors_copy_at), \
        ::codex_agent::detail::NativeSymbol::s233>::call
#define codex_agent_hook_catalog_errors_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_errors_count), \
        ::codex_agent::detail::NativeSymbol::s234>::call
#define codex_agent_hook_catalog_hooks_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_hooks_at), \
        ::codex_agent::detail::NativeSymbol::s235>::call
#define codex_agent_hook_catalog_hooks_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_hooks_count), \
        ::codex_agent::detail::NativeSymbol::s236>::call
#define codex_agent_hook_catalog_warnings_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_warnings_copy_at), \
        ::codex_agent::detail::NativeSymbol::s237>::call
#define codex_agent_hook_catalog_warnings_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_catalog_warnings_count), \
        ::codex_agent::detail::NativeSymbol::s238>::call
#define codex_agent_hook_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_create), \
        ::codex_agent::detail::NativeSymbol::s239>::call
#define codex_agent_hook_current_hash_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_current_hash_copy), \
        ::codex_agent::detail::NativeSymbol::s240>::call
#define codex_agent_hook_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_destroy), \
        ::codex_agent::detail::NativeSymbol::s241>::call
#define codex_agent_hook_event_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_event_name_copy), \
        ::codex_agent::detail::NativeSymbol::s242>::call
#define codex_agent_hook_handler \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler), \
        ::codex_agent::detail::NativeSymbol::s243>::call
#define codex_agent_hook_handler_agent_acquire \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_agent_acquire), \
        ::codex_agent::detail::NativeSymbol::s244>::call
#define codex_agent_hook_handler_agent_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_agent_destroy), \
        ::codex_agent::detail::NativeSymbol::s245>::call
#define codex_agent_hook_handler_command \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_command), \
        ::codex_agent::detail::NativeSymbol::s246>::call
#define codex_agent_hook_handler_command_command_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_command_command_copy), \
        ::codex_agent::detail::NativeSymbol::s247>::call
#define codex_agent_hook_handler_command_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_command_create), \
        ::codex_agent::detail::NativeSymbol::s248>::call
#define codex_agent_hook_handler_command_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_command_destroy), \
        ::codex_agent::detail::NativeSymbol::s249>::call
#define codex_agent_hook_handler_command_is_async \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_command_is_async), \
        ::codex_agent::detail::NativeSymbol::s250>::call
#define codex_agent_hook_handler_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_destroy), \
        ::codex_agent::detail::NativeSymbol::s251>::call
#define codex_agent_hook_handler_from_agent \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_from_agent), \
        ::codex_agent::detail::NativeSymbol::s252>::call
#define codex_agent_hook_handler_from_command \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_from_command), \
        ::codex_agent::detail::NativeSymbol::s253>::call
#define codex_agent_hook_handler_from_mcp_tool \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_from_mcp_tool), \
        ::codex_agent::detail::NativeSymbol::s254>::call
#define codex_agent_hook_handler_from_prompt \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_from_prompt), \
        ::codex_agent::detail::NativeSymbol::s255>::call
#define codex_agent_hook_handler_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_kind), \
        ::codex_agent::detail::NativeSymbol::s256>::call
#define codex_agent_hook_handler_mcp_tool \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_mcp_tool), \
        ::codex_agent::detail::NativeSymbol::s257>::call
#define codex_agent_hook_handler_mcp_tool_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_mcp_tool_create), \
        ::codex_agent::detail::NativeSymbol::s258>::call
#define codex_agent_hook_handler_mcp_tool_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_mcp_tool_destroy), \
        ::codex_agent::detail::NativeSymbol::s259>::call
#define codex_agent_hook_handler_mcp_tool_server_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_mcp_tool_server_copy), \
        ::codex_agent::detail::NativeSymbol::s260>::call
#define codex_agent_hook_handler_mcp_tool_tool_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_mcp_tool_tool_copy), \
        ::codex_agent::detail::NativeSymbol::s261>::call
#define codex_agent_hook_handler_prompt_acquire \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_prompt_acquire), \
        ::codex_agent::detail::NativeSymbol::s262>::call
#define codex_agent_hook_handler_prompt_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_handler_prompt_destroy), \
        ::codex_agent::detail::NativeSymbol::s263>::call
#define codex_agent_hook_has_matcher \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_has_matcher), \
        ::codex_agent::detail::NativeSymbol::s264>::call
#define codex_agent_hook_has_plugin_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_has_plugin_id), \
        ::codex_agent::detail::NativeSymbol::s265>::call
#define codex_agent_hook_has_status_message \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_has_status_message), \
        ::codex_agent::detail::NativeSymbol::s266>::call
#define codex_agent_hook_is_enabled \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_is_enabled), \
        ::codex_agent::detail::NativeSymbol::s267>::call
#define codex_agent_hook_is_managed \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_is_managed), \
        ::codex_agent::detail::NativeSymbol::s268>::call
#define codex_agent_hook_key_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_key_copy), \
        ::codex_agent::detail::NativeSymbol::s269>::call
#define codex_agent_hook_matcher_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_matcher_copy), \
        ::codex_agent::detail::NativeSymbol::s270>::call
#define codex_agent_hook_origin \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_origin), \
        ::codex_agent::detail::NativeSymbol::s271>::call
#define codex_agent_hook_plugin_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_plugin_id_copy), \
        ::codex_agent::detail::NativeSymbol::s272>::call
#define codex_agent_hook_source_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_source_copy), \
        ::codex_agent::detail::NativeSymbol::s273>::call
#define codex_agent_hook_source_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_source_path_copy), \
        ::codex_agent::detail::NativeSymbol::s274>::call
#define codex_agent_hook_status_message_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_status_message_copy), \
        ::codex_agent::detail::NativeSymbol::s275>::call
#define codex_agent_hook_timeout_seconds \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_timeout_seconds), \
        ::codex_agent::detail::NativeSymbol::s276>::call
#define codex_agent_hook_trust_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hook_trust_status), \
        ::codex_agent::detail::NativeSymbol::s277>::call
#define codex_agent_hooks_install \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_install), \
        ::codex_agent::detail::NativeSymbol::s278>::call
#define codex_agent_hooks_is_available \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_is_available), \
        ::codex_agent::detail::NativeSymbol::s279>::call
#define codex_agent_hooks_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_list), \
        ::codex_agent::detail::NativeSymbol::s280>::call
#define codex_agent_hooks_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_release), \
        ::codex_agent::detail::NativeSymbol::s281>::call
#define codex_agent_hooks_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_retain), \
        ::codex_agent::detail::NativeSymbol::s282>::call
#define codex_agent_hooks_trust \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_trust), \
        ::codex_agent::detail::NativeSymbol::s283>::call
#define codex_agent_hooks_uninstall \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_hooks_uninstall), \
        ::codex_agent::detail::NativeSymbol::s284>::call
#define codex_agent_host_close \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_close), \
        ::codex_agent::detail::NativeSymbol::s285>::call
#define codex_agent_host_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_create), \
        ::codex_agent::detail::NativeSymbol::s286>::call
#define codex_agent_host_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_release), \
        ::codex_agent::detail::NativeSymbol::s287>::call
#define codex_agent_host_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_retain), \
        ::codex_agent::detail::NativeSymbol::s288>::call
#define codex_agent_host_select_workspace \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_select_workspace), \
        ::codex_agent::detail::NativeSymbol::s289>::call
#define codex_agent_host_start \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_start), \
        ::codex_agent::detail::NativeSymbol::s290>::call
#define codex_agent_host_state_agent \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_agent), \
        ::codex_agent::detail::NativeSymbol::s291>::call
#define codex_agent_host_state_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_failure), \
        ::codex_agent::detail::NativeSymbol::s292>::call
#define codex_agent_host_state_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_get), \
        ::codex_agent::detail::NativeSymbol::s293>::call
#define codex_agent_host_state_has_workspace \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_has_workspace), \
        ::codex_agent::detail::NativeSymbol::s294>::call
#define codex_agent_host_state_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_kind), \
        ::codex_agent::detail::NativeSymbol::s295>::call
#define codex_agent_host_state_requirement_message_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_requirement_message_copy), \
        ::codex_agent::detail::NativeSymbol::s296>::call
#define codex_agent_host_state_requirement_reason \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_requirement_reason), \
        ::codex_agent::detail::NativeSymbol::s297>::call
#define codex_agent_host_state_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_subscribe), \
        ::codex_agent::detail::NativeSymbol::s298>::call
#define codex_agent_host_state_workspace_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_workspace_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s299>::call
#define codex_agent_host_state_workspace_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_host_state_workspace_path_copy), \
        ::codex_agent::detail::NativeSymbol::s300>::call
#define codex_agent_integration_authorization_active_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_active_get), \
        ::codex_agent::detail::NativeSymbol::s301>::call
#define codex_agent_integration_authorization_active_has_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_active_has_value), \
        ::codex_agent::detail::NativeSymbol::s302>::call
#define codex_agent_integration_authorization_active_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_active_subscribe), \
        ::codex_agent::detail::NativeSymbol::s303>::call
#define codex_agent_integration_authorization_active_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_active_value), \
        ::codex_agent::detail::NativeSymbol::s304>::call
#define codex_agent_integration_authorization_authorize \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_authorize), \
        ::codex_agent::detail::NativeSymbol::s305>::call
#define codex_agent_integration_authorization_cancel \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_cancel), \
        ::codex_agent::detail::NativeSymbol::s306>::call
#define codex_agent_integration_authorization_is_authorizing_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_is_authorizing_get), \
        ::codex_agent::detail::NativeSymbol::s307>::call
#define codex_agent_integration_authorization_is_authorizing_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_is_authorizing_subscribe), \
        ::codex_agent::detail::NativeSymbol::s308>::call
#define codex_agent_integration_authorization_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_release), \
        ::codex_agent::detail::NativeSymbol::s309>::call
#define codex_agent_integration_authorization_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_retain), \
        ::codex_agent::detail::NativeSymbol::s310>::call
#define codex_agent_integration_authorization_state_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_destroy), \
        ::codex_agent::detail::NativeSymbol::s311>::call
#define codex_agent_integration_authorization_state_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_failure), \
        ::codex_agent::detail::NativeSymbol::s312>::call
#define codex_agent_integration_authorization_state_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_get), \
        ::codex_agent::detail::NativeSymbol::s313>::call
#define codex_agent_integration_authorization_state_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_status), \
        ::codex_agent::detail::NativeSymbol::s314>::call
#define codex_agent_integration_authorization_state_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_subscribe), \
        ::codex_agent::detail::NativeSymbol::s315>::call
#define codex_agent_integration_authorization_state_target \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_target), \
        ::codex_agent::detail::NativeSymbol::s316>::call
#define codex_agent_integration_authorization_state_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_authorization_state_value), \
        ::codex_agent::detail::NativeSymbol::s317>::call
#define codex_agent_integration_connector \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_connector), \
        ::codex_agent::detail::NativeSymbol::s318>::call
#define codex_agent_integration_connector_connector \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_connector_connector), \
        ::codex_agent::detail::NativeSymbol::s319>::call
#define codex_agent_integration_connector_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_connector_create), \
        ::codex_agent::detail::NativeSymbol::s320>::call
#define codex_agent_integration_connector_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_connector_destroy), \
        ::codex_agent::detail::NativeSymbol::s321>::call
#define codex_agent_integration_connector_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_connector_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s322>::call
#define codex_agent_integration_connector_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_connector_id_copy), \
        ::codex_agent::detail::NativeSymbol::s323>::call
#define codex_agent_integration_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_destroy), \
        ::codex_agent::detail::NativeSymbol::s324>::call
#define codex_agent_integration_from_connector \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_from_connector), \
        ::codex_agent::detail::NativeSymbol::s325>::call
#define codex_agent_integration_from_mcp_server \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_from_mcp_server), \
        ::codex_agent::detail::NativeSymbol::s326>::call
#define codex_agent_integration_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_kind), \
        ::codex_agent::detail::NativeSymbol::s327>::call
#define codex_agent_integration_mcp_server \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_mcp_server), \
        ::codex_agent::detail::NativeSymbol::s328>::call
#define codex_agent_integration_mcp_server_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_mcp_server_create), \
        ::codex_agent::detail::NativeSymbol::s329>::call
#define codex_agent_integration_mcp_server_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_mcp_server_destroy), \
        ::codex_agent::detail::NativeSymbol::s330>::call
#define codex_agent_integration_mcp_server_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_mcp_server_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s331>::call
#define codex_agent_integration_mcp_server_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_mcp_server_id_copy), \
        ::codex_agent::detail::NativeSymbol::s332>::call
#define codex_agent_integration_mcp_server_server \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_integration_mcp_server_server), \
        ::codex_agent::detail::NativeSymbol::s333>::call
#define codex_agent_interaction_state_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_create), \
        ::codex_agent::detail::NativeSymbol::s334>::call
#define codex_agent_interaction_state_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_destroy), \
        ::codex_agent::detail::NativeSymbol::s335>::call
#define codex_agent_interaction_state_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_failure), \
        ::codex_agent::detail::NativeSymbol::s336>::call
#define codex_agent_interaction_state_has_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_has_failure), \
        ::codex_agent::detail::NativeSymbol::s337>::call
#define codex_agent_interaction_state_is_resolving \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_is_resolving), \
        ::codex_agent::detail::NativeSymbol::s338>::call
#define codex_agent_interaction_state_pending_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_pending_at), \
        ::codex_agent::detail::NativeSymbol::s339>::call
#define codex_agent_interaction_state_pending_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_pending_count), \
        ::codex_agent::detail::NativeSymbol::s340>::call
#define codex_agent_interaction_state_pending_for \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_pending_for), \
        ::codex_agent::detail::NativeSymbol::s341>::call
#define codex_agent_interaction_state_resolving_request_ids_contains \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interaction_state_resolving_request_ids_contains), \
        ::codex_agent::detail::NativeSymbol::s342>::call
#define codex_agent_interactions_approvals_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_approvals_at), \
        ::codex_agent::detail::NativeSymbol::s343>::call
#define codex_agent_interactions_approvals_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_approvals_count), \
        ::codex_agent::detail::NativeSymbol::s344>::call
#define codex_agent_interactions_approvals_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_approvals_get), \
        ::codex_agent::detail::NativeSymbol::s345>::call
#define codex_agent_interactions_approvals_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_approvals_subscribe), \
        ::codex_agent::detail::NativeSymbol::s346>::call
#define codex_agent_interactions_elicitations_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_elicitations_at), \
        ::codex_agent::detail::NativeSymbol::s347>::call
#define codex_agent_interactions_elicitations_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_elicitations_count), \
        ::codex_agent::detail::NativeSymbol::s348>::call
#define codex_agent_interactions_elicitations_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_elicitations_get), \
        ::codex_agent::detail::NativeSymbol::s349>::call
#define codex_agent_interactions_elicitations_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_elicitations_subscribe), \
        ::codex_agent::detail::NativeSymbol::s350>::call
#define codex_agent_interactions_open_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_open_url), \
        ::codex_agent::detail::NativeSymbol::s351>::call
#define codex_agent_interactions_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_release), \
        ::codex_agent::detail::NativeSymbol::s352>::call
#define codex_agent_interactions_resolve_approval \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_resolve_approval), \
        ::codex_agent::detail::NativeSymbol::s353>::call
#define codex_agent_interactions_resolve_elicitation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_resolve_elicitation), \
        ::codex_agent::detail::NativeSymbol::s354>::call
#define codex_agent_interactions_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_retain), \
        ::codex_agent::detail::NativeSymbol::s355>::call
#define codex_agent_interactions_state_get \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_state_get), \
        ::codex_agent::detail::NativeSymbol::s356>::call
#define codex_agent_interactions_state_subscribe \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_state_subscribe), \
        ::codex_agent::detail::NativeSymbol::s357>::call
#define codex_agent_interactions_state_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_interactions_state_value), \
        ::codex_agent::detail::NativeSymbol::s358>::call
#define codex_agent_invocation_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_destroy), \
        ::codex_agent::detail::NativeSymbol::s359>::call
#define codex_agent_invocation_from_plugin \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_from_plugin), \
        ::codex_agent::detail::NativeSymbol::s360>::call
#define codex_agent_invocation_from_skill \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_from_skill), \
        ::codex_agent::detail::NativeSymbol::s361>::call
#define codex_agent_invocation_key_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_key_copy), \
        ::codex_agent::detail::NativeSymbol::s362>::call
#define codex_agent_invocation_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_kind), \
        ::codex_agent::detail::NativeSymbol::s363>::call
#define codex_agent_invocation_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_name_copy), \
        ::codex_agent::detail::NativeSymbol::s364>::call
#define codex_agent_invocation_plugin \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_plugin), \
        ::codex_agent::detail::NativeSymbol::s365>::call
#define codex_agent_invocation_plugin_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_plugin_create), \
        ::codex_agent::detail::NativeSymbol::s366>::call
#define codex_agent_invocation_plugin_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_plugin_destroy), \
        ::codex_agent::detail::NativeSymbol::s367>::call
#define codex_agent_invocation_plugin_uri_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_plugin_uri_copy), \
        ::codex_agent::detail::NativeSymbol::s368>::call
#define codex_agent_invocation_skill \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_skill), \
        ::codex_agent::detail::NativeSymbol::s369>::call
#define codex_agent_invocation_skill_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_skill_create), \
        ::codex_agent::detail::NativeSymbol::s370>::call
#define codex_agent_invocation_skill_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_skill_destroy), \
        ::codex_agent::detail::NativeSymbol::s371>::call
#define codex_agent_invocation_skill_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_invocation_skill_path_copy), \
        ::codex_agent::detail::NativeSymbol::s372>::call
#define codex_agent_mcp_environment_variable_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_environment_variable_create), \
        ::codex_agent::detail::NativeSymbol::s373>::call
#define codex_agent_mcp_environment_variable_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_environment_variable_destroy), \
        ::codex_agent::detail::NativeSymbol::s374>::call
#define codex_agent_mcp_environment_variable_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_environment_variable_name_copy), \
        ::codex_agent::detail::NativeSymbol::s375>::call
#define codex_agent_mcp_environment_variable_source \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_environment_variable_source), \
        ::codex_agent::detail::NativeSymbol::s376>::call
#define codex_agent_mcp_oauth_configuration_callback_port \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_oauth_configuration_callback_port), \
        ::codex_agent::detail::NativeSymbol::s377>::call
#define codex_agent_mcp_oauth_configuration_client_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_oauth_configuration_client_id_copy), \
        ::codex_agent::detail::NativeSymbol::s378>::call
#define codex_agent_mcp_oauth_configuration_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_oauth_configuration_create), \
        ::codex_agent::detail::NativeSymbol::s379>::call
#define codex_agent_mcp_oauth_configuration_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_oauth_configuration_destroy), \
        ::codex_agent::detail::NativeSymbol::s380>::call
#define codex_agent_mcp_oauth_configuration_has_client_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_oauth_configuration_has_client_id), \
        ::codex_agent::detail::NativeSymbol::s381>::call
#define codex_agent_mcp_server_auth_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_auth_status), \
        ::codex_agent::detail::NativeSymbol::s382>::call
#define codex_agent_mcp_server_can_remove \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_can_remove), \
        ::codex_agent::detail::NativeSymbol::s383>::call
#define codex_agent_mcp_server_configuration \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration), \
        ::codex_agent::detail::NativeSymbol::s384>::call
#define codex_agent_mcp_server_configuration_authentication \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_authentication), \
        ::codex_agent::detail::NativeSymbol::s385>::call
#define codex_agent_mcp_server_configuration_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_create), \
        ::codex_agent::detail::NativeSymbol::s386>::call
#define codex_agent_mcp_server_configuration_default_tool_approval \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_default_tool_approval), \
        ::codex_agent::detail::NativeSymbol::s387>::call
#define codex_agent_mcp_server_configuration_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_destroy), \
        ::codex_agent::detail::NativeSymbol::s388>::call
#define codex_agent_mcp_server_configuration_disabled_tool_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_disabled_tool_copy_at), \
        ::codex_agent::detail::NativeSymbol::s389>::call
#define codex_agent_mcp_server_configuration_disabled_tools_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_disabled_tools_count), \
        ::codex_agent::detail::NativeSymbol::s390>::call
#define codex_agent_mcp_server_configuration_enabled_tool_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_enabled_tool_copy_at), \
        ::codex_agent::detail::NativeSymbol::s391>::call
#define codex_agent_mcp_server_configuration_enabled_tools_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_enabled_tools_count), \
        ::codex_agent::detail::NativeSymbol::s392>::call
#define codex_agent_mcp_server_configuration_environment_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_environment_id_copy), \
        ::codex_agent::detail::NativeSymbol::s393>::call
#define codex_agent_mcp_server_configuration_has_disabled_tools \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_has_disabled_tools), \
        ::codex_agent::detail::NativeSymbol::s394>::call
#define codex_agent_mcp_server_configuration_has_enabled_tools \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_has_enabled_tools), \
        ::codex_agent::detail::NativeSymbol::s395>::call
#define codex_agent_mcp_server_configuration_has_oauth \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_has_oauth), \
        ::codex_agent::detail::NativeSymbol::s396>::call
#define codex_agent_mcp_server_configuration_has_oauth_resource \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_has_oauth_resource), \
        ::codex_agent::detail::NativeSymbol::s397>::call
#define codex_agent_mcp_server_configuration_has_omit_tools_from \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_has_omit_tools_from), \
        ::codex_agent::detail::NativeSymbol::s398>::call
#define codex_agent_mcp_server_configuration_has_scopes \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_has_scopes), \
        ::codex_agent::detail::NativeSymbol::s399>::call
#define codex_agent_mcp_server_configuration_is_enabled \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_is_enabled), \
        ::codex_agent::detail::NativeSymbol::s400>::call
#define codex_agent_mcp_server_configuration_is_required \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_is_required), \
        ::codex_agent::detail::NativeSymbol::s401>::call
#define codex_agent_mcp_server_configuration_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_name_copy), \
        ::codex_agent::detail::NativeSymbol::s402>::call
#define codex_agent_mcp_server_configuration_oauth \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_oauth), \
        ::codex_agent::detail::NativeSymbol::s403>::call
#define codex_agent_mcp_server_configuration_oauth_resource_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_oauth_resource_copy), \
        ::codex_agent::detail::NativeSymbol::s404>::call
#define codex_agent_mcp_server_configuration_omit_tools_from_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_omit_tools_from_at), \
        ::codex_agent::detail::NativeSymbol::s405>::call
#define codex_agent_mcp_server_configuration_omit_tools_from_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_omit_tools_from_count), \
        ::codex_agent::detail::NativeSymbol::s406>::call
#define codex_agent_mcp_server_configuration_scope_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_scope_copy_at), \
        ::codex_agent::detail::NativeSymbol::s407>::call
#define codex_agent_mcp_server_configuration_scopes_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_scopes_count), \
        ::codex_agent::detail::NativeSymbol::s408>::call
#define codex_agent_mcp_server_configuration_startup_timeout_seconds \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_startup_timeout_seconds), \
        ::codex_agent::detail::NativeSymbol::s409>::call
#define codex_agent_mcp_server_configuration_supports_parallel_tool_calls \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_supports_parallel_tool_calls), \
        ::codex_agent::detail::NativeSymbol::s410>::call
#define codex_agent_mcp_server_configuration_tool_timeout_seconds \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_tool_timeout_seconds), \
        ::codex_agent::detail::NativeSymbol::s411>::call
#define codex_agent_mcp_server_configuration_tools_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_tools_count), \
        ::codex_agent::detail::NativeSymbol::s412>::call
#define codex_agent_mcp_server_configuration_tools_key_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_tools_key_copy_at), \
        ::codex_agent::detail::NativeSymbol::s413>::call
#define codex_agent_mcp_server_configuration_tools_value_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_tools_value_at), \
        ::codex_agent::detail::NativeSymbol::s414>::call
#define codex_agent_mcp_server_configuration_transport \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_configuration_transport), \
        ::codex_agent::detail::NativeSymbol::s415>::call
#define codex_agent_mcp_server_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_create), \
        ::codex_agent::detail::NativeSymbol::s416>::call
#define codex_agent_mcp_server_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_destroy), \
        ::codex_agent::detail::NativeSymbol::s417>::call
#define codex_agent_mcp_server_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s418>::call
#define codex_agent_mcp_server_has_configuration \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_has_configuration), \
        ::codex_agent::detail::NativeSymbol::s419>::call
#define codex_agent_mcp_server_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_name_copy), \
        ::codex_agent::detail::NativeSymbol::s420>::call
#define codex_agent_mcp_server_origin \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_server_origin), \
        ::codex_agent::detail::NativeSymbol::s421>::call
#define codex_agent_mcp_servers_add \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_servers_add), \
        ::codex_agent::detail::NativeSymbol::s422>::call
#define codex_agent_mcp_servers_is_available \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_servers_is_available), \
        ::codex_agent::detail::NativeSymbol::s423>::call
#define codex_agent_mcp_servers_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_servers_list), \
        ::codex_agent::detail::NativeSymbol::s424>::call
#define codex_agent_mcp_servers_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_servers_release), \
        ::codex_agent::detail::NativeSymbol::s425>::call
#define codex_agent_mcp_servers_remove \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_servers_remove), \
        ::codex_agent::detail::NativeSymbol::s426>::call
#define codex_agent_mcp_servers_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_servers_retain), \
        ::codex_agent::detail::NativeSymbol::s427>::call
#define codex_agent_mcp_tool_configuration_approval \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_tool_configuration_approval), \
        ::codex_agent::detail::NativeSymbol::s428>::call
#define codex_agent_mcp_tool_configuration_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_tool_configuration_create), \
        ::codex_agent::detail::NativeSymbol::s429>::call
#define codex_agent_mcp_tool_configuration_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_tool_configuration_destroy), \
        ::codex_agent::detail::NativeSymbol::s430>::call
#define codex_agent_mcp_transport_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_destroy), \
        ::codex_agent::detail::NativeSymbol::s431>::call
#define codex_agent_mcp_transport_from_http \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_from_http), \
        ::codex_agent::detail::NativeSymbol::s432>::call
#define codex_agent_mcp_transport_from_stdio \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_from_stdio), \
        ::codex_agent::detail::NativeSymbol::s433>::call
#define codex_agent_mcp_transport_http \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http), \
        ::codex_agent::detail::NativeSymbol::s434>::call
#define codex_agent_mcp_transport_http_bearer_token_environment_variable_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_bearer_token_environment_variable_copy), \
        ::codex_agent::detail::NativeSymbol::s435>::call
#define codex_agent_mcp_transport_http_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_create), \
        ::codex_agent::detail::NativeSymbol::s436>::call
#define codex_agent_mcp_transport_http_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_destroy), \
        ::codex_agent::detail::NativeSymbol::s437>::call
#define codex_agent_mcp_transport_http_environment_headers_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_environment_headers_count), \
        ::codex_agent::detail::NativeSymbol::s438>::call
#define codex_agent_mcp_transport_http_environment_headers_key_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_environment_headers_key_copy_at), \
        ::codex_agent::detail::NativeSymbol::s439>::call
#define codex_agent_mcp_transport_http_environment_headers_value_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_environment_headers_value_copy_at), \
        ::codex_agent::detail::NativeSymbol::s440>::call
#define codex_agent_mcp_transport_http_has_bearer_token_environment_variable \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_has_bearer_token_environment_variable), \
        ::codex_agent::detail::NativeSymbol::s441>::call
#define codex_agent_mcp_transport_http_has_environment_headers \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_has_environment_headers), \
        ::codex_agent::detail::NativeSymbol::s442>::call
#define codex_agent_mcp_transport_http_has_headers \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_has_headers), \
        ::codex_agent::detail::NativeSymbol::s443>::call
#define codex_agent_mcp_transport_http_has_headers_helper \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_has_headers_helper), \
        ::codex_agent::detail::NativeSymbol::s444>::call
#define codex_agent_mcp_transport_http_headers_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_headers_count), \
        ::codex_agent::detail::NativeSymbol::s445>::call
#define codex_agent_mcp_transport_http_headers_helper_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_headers_helper_copy), \
        ::codex_agent::detail::NativeSymbol::s446>::call
#define codex_agent_mcp_transport_http_headers_key_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_headers_key_copy_at), \
        ::codex_agent::detail::NativeSymbol::s447>::call
#define codex_agent_mcp_transport_http_headers_value_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_headers_value_copy_at), \
        ::codex_agent::detail::NativeSymbol::s448>::call
#define codex_agent_mcp_transport_http_url_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_http_url_copy), \
        ::codex_agent::detail::NativeSymbol::s449>::call
#define codex_agent_mcp_transport_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_kind), \
        ::codex_agent::detail::NativeSymbol::s450>::call
#define codex_agent_mcp_transport_stdio \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio), \
        ::codex_agent::detail::NativeSymbol::s451>::call
#define codex_agent_mcp_transport_stdio_argument_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_argument_copy_at), \
        ::codex_agent::detail::NativeSymbol::s452>::call
#define codex_agent_mcp_transport_stdio_arguments_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_arguments_count), \
        ::codex_agent::detail::NativeSymbol::s453>::call
#define codex_agent_mcp_transport_stdio_command_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_command_copy), \
        ::codex_agent::detail::NativeSymbol::s454>::call
#define codex_agent_mcp_transport_stdio_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_create), \
        ::codex_agent::detail::NativeSymbol::s455>::call
#define codex_agent_mcp_transport_stdio_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_destroy), \
        ::codex_agent::detail::NativeSymbol::s456>::call
#define codex_agent_mcp_transport_stdio_environment_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_environment_count), \
        ::codex_agent::detail::NativeSymbol::s457>::call
#define codex_agent_mcp_transport_stdio_environment_key_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_environment_key_copy_at), \
        ::codex_agent::detail::NativeSymbol::s458>::call
#define codex_agent_mcp_transport_stdio_environment_value_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_environment_value_copy_at), \
        ::codex_agent::detail::NativeSymbol::s459>::call
#define codex_agent_mcp_transport_stdio_forwarded_environment_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_forwarded_environment_at), \
        ::codex_agent::detail::NativeSymbol::s460>::call
#define codex_agent_mcp_transport_stdio_forwarded_environment_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_forwarded_environment_count), \
        ::codex_agent::detail::NativeSymbol::s461>::call
#define codex_agent_mcp_transport_stdio_has_environment \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_has_environment), \
        ::codex_agent::detail::NativeSymbol::s462>::call
#define codex_agent_mcp_transport_stdio_has_working_directory \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_has_working_directory), \
        ::codex_agent::detail::NativeSymbol::s463>::call
#define codex_agent_mcp_transport_stdio_working_directory_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_mcp_transport_stdio_working_directory_copy), \
        ::codex_agent::detail::NativeSymbol::s464>::call
#define codex_agent_message_capabilities_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_capabilities_count), \
        ::codex_agent::detail::NativeSymbol::s465>::call
#define codex_agent_message_client_message_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_client_message_id_copy), \
        ::codex_agent::detail::NativeSymbol::s466>::call
#define codex_agent_message_collaboration_mode \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_collaboration_mode), \
        ::codex_agent::detail::NativeSymbol::s467>::call
#define codex_agent_message_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_destroy), \
        ::codex_agent::detail::NativeSymbol::s468>::call
#define codex_agent_message_exit_code \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_exit_code), \
        ::codex_agent::detail::NativeSymbol::s469>::call
#define codex_agent_message_has_capability \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_has_capability), \
        ::codex_agent::detail::NativeSymbol::s470>::call
#define codex_agent_message_has_client_message_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_has_client_message_id), \
        ::codex_agent::detail::NativeSymbol::s471>::call
#define codex_agent_message_has_plan \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_has_plan), \
        ::codex_agent::detail::NativeSymbol::s472>::call
#define codex_agent_message_has_reasoning \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_has_reasoning), \
        ::codex_agent::detail::NativeSymbol::s473>::call
#define codex_agent_message_has_shell_command \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_has_shell_command), \
        ::codex_agent::detail::NativeSymbol::s474>::call
#define codex_agent_message_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_id_copy), \
        ::codex_agent::detail::NativeSymbol::s475>::call
#define codex_agent_message_invocation_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_invocation_at), \
        ::codex_agent::detail::NativeSymbol::s476>::call
#define codex_agent_message_invocations_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_invocations_count), \
        ::codex_agent::detail::NativeSymbol::s477>::call
#define codex_agent_message_plan_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_plan_copy), \
        ::codex_agent::detail::NativeSymbol::s478>::call
#define codex_agent_message_reasoning_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_reasoning_copy), \
        ::codex_agent::detail::NativeSymbol::s479>::call
#define codex_agent_message_role \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_role), \
        ::codex_agent::detail::NativeSymbol::s480>::call
#define codex_agent_message_shell_command_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_shell_command_copy), \
        ::codex_agent::detail::NativeSymbol::s481>::call
#define codex_agent_message_text_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_message_text_copy), \
        ::codex_agent::detail::NativeSymbol::s482>::call
#define codex_agent_model_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_create), \
        ::codex_agent::detail::NativeSymbol::s483>::call
#define codex_agent_model_default_effort_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_default_effort_copy), \
        ::codex_agent::detail::NativeSymbol::s484>::call
#define codex_agent_model_default_service_tier_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_default_service_tier_copy), \
        ::codex_agent::detail::NativeSymbol::s485>::call
#define codex_agent_model_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_description_copy), \
        ::codex_agent::detail::NativeSymbol::s486>::call
#define codex_agent_model_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_destroy), \
        ::codex_agent::detail::NativeSymbol::s487>::call
#define codex_agent_model_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s488>::call
#define codex_agent_model_has_default_service_tier \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_has_default_service_tier), \
        ::codex_agent::detail::NativeSymbol::s489>::call
#define codex_agent_model_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_id_copy), \
        ::codex_agent::detail::NativeSymbol::s490>::call
#define codex_agent_model_is_default \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_is_default), \
        ::codex_agent::detail::NativeSymbol::s491>::call
#define codex_agent_model_service_tier_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_service_tier_at), \
        ::codex_agent::detail::NativeSymbol::s492>::call
#define codex_agent_model_service_tiers_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_service_tiers_count), \
        ::codex_agent::detail::NativeSymbol::s493>::call
#define codex_agent_model_supported_effort_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_supported_effort_copy_at), \
        ::codex_agent::detail::NativeSymbol::s494>::call
#define codex_agent_model_supported_efforts_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_model_supported_efforts_count), \
        ::codex_agent::detail::NativeSymbol::s495>::call
#define codex_agent_models_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_models_list), \
        ::codex_agent::detail::NativeSymbol::s496>::call
#define codex_agent_models_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_models_release), \
        ::codex_agent::detail::NativeSymbol::s497>::call
#define codex_agent_models_resolve \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_models_resolve), \
        ::codex_agent::detail::NativeSymbol::s498>::call
#define codex_agent_models_resolve_effort \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_models_resolve_effort), \
        ::codex_agent::detail::NativeSymbol::s499>::call
#define codex_agent_models_resolve_service_tier \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_models_resolve_service_tier), \
        ::codex_agent::detail::NativeSymbol::s500>::call
#define codex_agent_models_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_models_retain), \
        ::codex_agent::detail::NativeSymbol::s501>::call
#define codex_agent_operation_cancel \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_cancel), \
        ::codex_agent::detail::NativeSymbol::s502>::call
#define codex_agent_operation_connector_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_connector_at), \
        ::codex_agent::detail::NativeSymbol::s503>::call
#define codex_agent_operation_connectors_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_connectors_count), \
        ::codex_agent::detail::NativeSymbol::s504>::call
#define codex_agent_operation_conversation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_conversation), \
        ::codex_agent::detail::NativeSymbol::s505>::call
#define codex_agent_operation_conversation_summaries_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_conversation_summaries_count), \
        ::codex_agent::detail::NativeSymbol::s506>::call
#define codex_agent_operation_conversation_summary_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_conversation_summary_at), \
        ::codex_agent::detail::NativeSymbol::s507>::call
#define codex_agent_operation_conversation_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_conversation_value), \
        ::codex_agent::detail::NativeSymbol::s508>::call
#define codex_agent_operation_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_destroy), \
        ::codex_agent::detail::NativeSymbol::s509>::call
#define codex_agent_operation_failure \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_failure), \
        ::codex_agent::detail::NativeSymbol::s510>::call
#define codex_agent_operation_has_service_tier \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_has_service_tier), \
        ::codex_agent::detail::NativeSymbol::s511>::call
#define codex_agent_operation_hook \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_hook), \
        ::codex_agent::detail::NativeSymbol::s512>::call
#define codex_agent_operation_hook_catalog \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_hook_catalog), \
        ::codex_agent::detail::NativeSymbol::s513>::call
#define codex_agent_operation_mcp_server \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_mcp_server), \
        ::codex_agent::detail::NativeSymbol::s514>::call
#define codex_agent_operation_mcp_server_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_mcp_server_at), \
        ::codex_agent::detail::NativeSymbol::s515>::call
#define codex_agent_operation_mcp_servers_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_mcp_servers_count), \
        ::codex_agent::detail::NativeSymbol::s516>::call
#define codex_agent_operation_model \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_model), \
        ::codex_agent::detail::NativeSymbol::s517>::call
#define codex_agent_operation_model_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_model_at), \
        ::codex_agent::detail::NativeSymbol::s518>::call
#define codex_agent_operation_models_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_models_count), \
        ::codex_agent::detail::NativeSymbol::s519>::call
#define codex_agent_operation_plugin_catalog \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_plugin_catalog), \
        ::codex_agent::detail::NativeSymbol::s520>::call
#define codex_agent_operation_plugin_detail \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_plugin_detail), \
        ::codex_agent::detail::NativeSymbol::s521>::call
#define codex_agent_operation_plugin_install_result \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_plugin_install_result), \
        ::codex_agent::detail::NativeSymbol::s522>::call
#define codex_agent_operation_result \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_result), \
        ::codex_agent::detail::NativeSymbol::s523>::call
#define codex_agent_operation_service_tier \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_service_tier), \
        ::codex_agent::detail::NativeSymbol::s524>::call
#define codex_agent_operation_skill \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_skill), \
        ::codex_agent::detail::NativeSymbol::s525>::call
#define codex_agent_operation_skill_catalog \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_skill_catalog), \
        ::codex_agent::detail::NativeSymbol::s526>::call
#define codex_agent_operation_skill_chunk \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_skill_chunk), \
        ::codex_agent::detail::NativeSymbol::s527>::call
#define codex_agent_operation_string_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_operation_string_copy), \
        ::codex_agent::detail::NativeSymbol::s528>::call
#define codex_agent_pending_approval_conversation_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_approval_conversation_id), \
        ::codex_agent::detail::NativeSymbol::s529>::call
#define codex_agent_pending_approval_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_approval_create), \
        ::codex_agent::detail::NativeSymbol::s530>::call
#define codex_agent_pending_approval_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_approval_destroy), \
        ::codex_agent::detail::NativeSymbol::s531>::call
#define codex_agent_pending_approval_details_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_approval_details_copy), \
        ::codex_agent::detail::NativeSymbol::s532>::call
#define codex_agent_pending_approval_request_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_approval_request_id_copy), \
        ::codex_agent::detail::NativeSymbol::s533>::call
#define codex_agent_pending_approval_title_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_approval_title_copy), \
        ::codex_agent::detail::NativeSymbol::s534>::call
#define codex_agent_pending_elicitation_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_elicitation_create), \
        ::codex_agent::detail::NativeSymbol::s535>::call
#define codex_agent_pending_elicitation_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_elicitation_destroy), \
        ::codex_agent::detail::NativeSymbol::s536>::call
#define codex_agent_pending_elicitation_elicitation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_elicitation_elicitation), \
        ::codex_agent::detail::NativeSymbol::s537>::call
#define codex_agent_pending_interaction_approval \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_approval), \
        ::codex_agent::detail::NativeSymbol::s538>::call
#define codex_agent_pending_interaction_conversation_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_conversation_id), \
        ::codex_agent::detail::NativeSymbol::s539>::call
#define codex_agent_pending_interaction_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_destroy), \
        ::codex_agent::detail::NativeSymbol::s540>::call
#define codex_agent_pending_interaction_elicitation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_elicitation), \
        ::codex_agent::detail::NativeSymbol::s541>::call
#define codex_agent_pending_interaction_from_approval \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_from_approval), \
        ::codex_agent::detail::NativeSymbol::s542>::call
#define codex_agent_pending_interaction_from_elicitation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_from_elicitation), \
        ::codex_agent::detail::NativeSymbol::s543>::call
#define codex_agent_pending_interaction_kind \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_kind), \
        ::codex_agent::detail::NativeSymbol::s544>::call
#define codex_agent_pending_interaction_list_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_list_at), \
        ::codex_agent::detail::NativeSymbol::s545>::call
#define codex_agent_pending_interaction_list_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_list_count), \
        ::codex_agent::detail::NativeSymbol::s546>::call
#define codex_agent_pending_interaction_list_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_list_destroy), \
        ::codex_agent::detail::NativeSymbol::s547>::call
#define codex_agent_pending_interaction_request_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_pending_interaction_request_id_copy), \
        ::codex_agent::detail::NativeSymbol::s548>::call
#define codex_agent_plan_progress_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_progress_destroy), \
        ::codex_agent::detail::NativeSymbol::s549>::call
#define codex_agent_plan_progress_explanation_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_progress_explanation_copy), \
        ::codex_agent::detail::NativeSymbol::s550>::call
#define codex_agent_plan_progress_has_explanation \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_progress_has_explanation), \
        ::codex_agent::detail::NativeSymbol::s551>::call
#define codex_agent_plan_progress_step_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_progress_step_at), \
        ::codex_agent::detail::NativeSymbol::s552>::call
#define codex_agent_plan_progress_steps_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_progress_steps_count), \
        ::codex_agent::detail::NativeSymbol::s553>::call
#define codex_agent_plan_step_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_step_destroy), \
        ::codex_agent::detail::NativeSymbol::s554>::call
#define codex_agent_plan_step_status \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_step_status), \
        ::codex_agent::detail::NativeSymbol::s555>::call
#define codex_agent_plan_step_text_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plan_step_text_copy), \
        ::codex_agent::detail::NativeSymbol::s556>::call
#define codex_agent_plugin_catalog_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_catalog_destroy), \
        ::codex_agent::detail::NativeSymbol::s557>::call
#define codex_agent_plugin_catalog_errors_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_catalog_errors_copy_at), \
        ::codex_agent::detail::NativeSymbol::s558>::call
#define codex_agent_plugin_catalog_errors_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_catalog_errors_count), \
        ::codex_agent::detail::NativeSymbol::s559>::call
#define codex_agent_plugin_catalog_freshness \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_catalog_freshness), \
        ::codex_agent::detail::NativeSymbol::s560>::call
#define codex_agent_plugin_catalog_plugins_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_catalog_plugins_at), \
        ::codex_agent::detail::NativeSymbol::s561>::call
#define codex_agent_plugin_catalog_plugins_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_catalog_plugins_count), \
        ::codex_agent::detail::NativeSymbol::s562>::call
#define codex_agent_plugin_detail_connectors_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_connectors_at), \
        ::codex_agent::detail::NativeSymbol::s563>::call
#define codex_agent_plugin_detail_connectors_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_connectors_count), \
        ::codex_agent::detail::NativeSymbol::s564>::call
#define codex_agent_plugin_detail_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_description_copy), \
        ::codex_agent::detail::NativeSymbol::s565>::call
#define codex_agent_plugin_detail_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_destroy), \
        ::codex_agent::detail::NativeSymbol::s566>::call
#define codex_agent_plugin_detail_hook_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_hook_count), \
        ::codex_agent::detail::NativeSymbol::s567>::call
#define codex_agent_plugin_detail_mcp_servers_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_mcp_servers_copy_at), \
        ::codex_agent::detail::NativeSymbol::s568>::call
#define codex_agent_plugin_detail_mcp_servers_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_mcp_servers_count), \
        ::codex_agent::detail::NativeSymbol::s569>::call
#define codex_agent_plugin_detail_skills_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_skills_at), \
        ::codex_agent::detail::NativeSymbol::s570>::call
#define codex_agent_plugin_detail_skills_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_skills_count), \
        ::codex_agent::detail::NativeSymbol::s571>::call
#define codex_agent_plugin_detail_summary \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_detail_summary), \
        ::codex_agent::detail::NativeSymbol::s572>::call
#define codex_agent_plugin_install_result_auth_policy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_install_result_auth_policy), \
        ::codex_agent::detail::NativeSymbol::s573>::call
#define codex_agent_plugin_install_result_connectors_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_install_result_connectors_at), \
        ::codex_agent::detail::NativeSymbol::s574>::call
#define codex_agent_plugin_install_result_connectors_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_install_result_connectors_count), \
        ::codex_agent::detail::NativeSymbol::s575>::call
#define codex_agent_plugin_install_result_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_install_result_destroy), \
        ::codex_agent::detail::NativeSymbol::s576>::call
#define codex_agent_plugin_install_result_has_message \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_install_result_has_message), \
        ::codex_agent::detail::NativeSymbol::s577>::call
#define codex_agent_plugin_install_result_message_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_install_result_message_copy), \
        ::codex_agent::detail::NativeSymbol::s578>::call
#define codex_agent_plugin_reference_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_create), \
        ::codex_agent::detail::NativeSymbol::s579>::call
#define codex_agent_plugin_reference_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_destroy), \
        ::codex_agent::detail::NativeSymbol::s580>::call
#define codex_agent_plugin_reference_has_marketplace_path \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_has_marketplace_path), \
        ::codex_agent::detail::NativeSymbol::s581>::call
#define codex_agent_plugin_reference_has_remote_plugin_id \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_has_remote_plugin_id), \
        ::codex_agent::detail::NativeSymbol::s582>::call
#define codex_agent_plugin_reference_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_id_copy), \
        ::codex_agent::detail::NativeSymbol::s583>::call
#define codex_agent_plugin_reference_marketplace_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_marketplace_name_copy), \
        ::codex_agent::detail::NativeSymbol::s584>::call
#define codex_agent_plugin_reference_marketplace_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_marketplace_path_copy), \
        ::codex_agent::detail::NativeSymbol::s585>::call
#define codex_agent_plugin_reference_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_name_copy), \
        ::codex_agent::detail::NativeSymbol::s586>::call
#define codex_agent_plugin_reference_remote_plugin_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_reference_remote_plugin_id_copy), \
        ::codex_agent::detail::NativeSymbol::s587>::call
#define codex_agent_plugin_skill_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_skill_description_copy), \
        ::codex_agent::detail::NativeSymbol::s588>::call
#define codex_agent_plugin_skill_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_skill_destroy), \
        ::codex_agent::detail::NativeSymbol::s589>::call
#define codex_agent_plugin_skill_has_path \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_skill_has_path), \
        ::codex_agent::detail::NativeSymbol::s590>::call
#define codex_agent_plugin_skill_is_enabled \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_skill_is_enabled), \
        ::codex_agent::detail::NativeSymbol::s591>::call
#define codex_agent_plugin_skill_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_skill_name_copy), \
        ::codex_agent::detail::NativeSymbol::s592>::call
#define codex_agent_plugin_skill_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_skill_path_copy), \
        ::codex_agent::detail::NativeSymbol::s593>::call
#define codex_agent_plugin_summary_auth_policy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_auth_policy), \
        ::codex_agent::detail::NativeSymbol::s594>::call
#define codex_agent_plugin_summary_brand_color_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_brand_color_copy), \
        ::codex_agent::detail::NativeSymbol::s595>::call
#define codex_agent_plugin_summary_capabilities_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_capabilities_copy_at), \
        ::codex_agent::detail::NativeSymbol::s596>::call
#define codex_agent_plugin_summary_capabilities_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_capabilities_count), \
        ::codex_agent::detail::NativeSymbol::s597>::call
#define codex_agent_plugin_summary_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_description_copy), \
        ::codex_agent::detail::NativeSymbol::s598>::call
#define codex_agent_plugin_summary_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_destroy), \
        ::codex_agent::detail::NativeSymbol::s599>::call
#define codex_agent_plugin_summary_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s600>::call
#define codex_agent_plugin_summary_has_brand_color \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_has_brand_color), \
        ::codex_agent::detail::NativeSymbol::s601>::call
#define codex_agent_plugin_summary_has_privacy_policy_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_has_privacy_policy_url), \
        ::codex_agent::detail::NativeSymbol::s602>::call
#define codex_agent_plugin_summary_has_terms_of_service_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_has_terms_of_service_url), \
        ::codex_agent::detail::NativeSymbol::s603>::call
#define codex_agent_plugin_summary_has_website_url \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_has_website_url), \
        ::codex_agent::detail::NativeSymbol::s604>::call
#define codex_agent_plugin_summary_install_policy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_install_policy), \
        ::codex_agent::detail::NativeSymbol::s605>::call
#define codex_agent_plugin_summary_is_available \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_is_available), \
        ::codex_agent::detail::NativeSymbol::s606>::call
#define codex_agent_plugin_summary_is_enabled \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_is_enabled), \
        ::codex_agent::detail::NativeSymbol::s607>::call
#define codex_agent_plugin_summary_is_installed \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_is_installed), \
        ::codex_agent::detail::NativeSymbol::s608>::call
#define codex_agent_plugin_summary_privacy_policy_url_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_privacy_policy_url_copy), \
        ::codex_agent::detail::NativeSymbol::s609>::call
#define codex_agent_plugin_summary_reference \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_reference), \
        ::codex_agent::detail::NativeSymbol::s610>::call
#define codex_agent_plugin_summary_terms_of_service_url_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_terms_of_service_url_copy), \
        ::codex_agent::detail::NativeSymbol::s611>::call
#define codex_agent_plugin_summary_website_url_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugin_summary_website_url_copy), \
        ::codex_agent::detail::NativeSymbol::s612>::call
#define codex_agent_plugins_install \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_install), \
        ::codex_agent::detail::NativeSymbol::s613>::call
#define codex_agent_plugins_is_available \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_is_available), \
        ::codex_agent::detail::NativeSymbol::s614>::call
#define codex_agent_plugins_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_list), \
        ::codex_agent::detail::NativeSymbol::s615>::call
#define codex_agent_plugins_read \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_read), \
        ::codex_agent::detail::NativeSymbol::s616>::call
#define codex_agent_plugins_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_release), \
        ::codex_agent::detail::NativeSymbol::s617>::call
#define codex_agent_plugins_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_retain), \
        ::codex_agent::detail::NativeSymbol::s618>::call
#define codex_agent_plugins_uninstall \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_plugins_uninstall), \
        ::codex_agent::detail::NativeSymbol::s619>::call
#define codex_agent_service_tier_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_service_tier_create), \
        ::codex_agent::detail::NativeSymbol::s620>::call
#define codex_agent_service_tier_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_service_tier_description_copy), \
        ::codex_agent::detail::NativeSymbol::s621>::call
#define codex_agent_service_tier_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_service_tier_destroy), \
        ::codex_agent::detail::NativeSymbol::s622>::call
#define codex_agent_service_tier_id_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_service_tier_id_copy), \
        ::codex_agent::detail::NativeSymbol::s623>::call
#define codex_agent_service_tier_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_service_tier_name_copy), \
        ::codex_agent::detail::NativeSymbol::s624>::call
#define codex_agent_skill_brand_color_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_brand_color_copy), \
        ::codex_agent::detail::NativeSymbol::s625>::call
#define codex_agent_skill_can_uninstall \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_can_uninstall), \
        ::codex_agent::detail::NativeSymbol::s626>::call
#define codex_agent_skill_catalog_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_catalog_destroy), \
        ::codex_agent::detail::NativeSymbol::s627>::call
#define codex_agent_skill_catalog_errors_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_catalog_errors_copy_at), \
        ::codex_agent::detail::NativeSymbol::s628>::call
#define codex_agent_skill_catalog_errors_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_catalog_errors_count), \
        ::codex_agent::detail::NativeSymbol::s629>::call
#define codex_agent_skill_catalog_skills_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_catalog_skills_at), \
        ::codex_agent::detail::NativeSymbol::s630>::call
#define codex_agent_skill_catalog_skills_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_catalog_skills_count), \
        ::codex_agent::detail::NativeSymbol::s631>::call
#define codex_agent_skill_chunk_content_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_chunk_content_copy), \
        ::codex_agent::detail::NativeSymbol::s632>::call
#define codex_agent_skill_chunk_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_chunk_destroy), \
        ::codex_agent::detail::NativeSymbol::s633>::call
#define codex_agent_skill_chunk_next_offset \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_chunk_next_offset), \
        ::codex_agent::detail::NativeSymbol::s634>::call
#define codex_agent_skill_chunk_total_bytes \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_chunk_total_bytes), \
        ::codex_agent::detail::NativeSymbol::s635>::call
#define codex_agent_skill_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_create), \
        ::codex_agent::detail::NativeSymbol::s636>::call
#define codex_agent_skill_dependencies_copy_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_dependencies_copy_at), \
        ::codex_agent::detail::NativeSymbol::s637>::call
#define codex_agent_skill_dependencies_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_dependencies_count), \
        ::codex_agent::detail::NativeSymbol::s638>::call
#define codex_agent_skill_description_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_description_copy), \
        ::codex_agent::detail::NativeSymbol::s639>::call
#define codex_agent_skill_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_destroy), \
        ::codex_agent::detail::NativeSymbol::s640>::call
#define codex_agent_skill_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s641>::call
#define codex_agent_skill_has_brand_color \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_has_brand_color), \
        ::codex_agent::detail::NativeSymbol::s642>::call
#define codex_agent_skill_is_enabled \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_is_enabled), \
        ::codex_agent::detail::NativeSymbol::s643>::call
#define codex_agent_skill_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_name_copy), \
        ::codex_agent::detail::NativeSymbol::s644>::call
#define codex_agent_skill_origin \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_origin), \
        ::codex_agent::detail::NativeSymbol::s645>::call
#define codex_agent_skill_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_path_copy), \
        ::codex_agent::detail::NativeSymbol::s646>::call
#define codex_agent_skill_scope \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skill_scope), \
        ::codex_agent::detail::NativeSymbol::s647>::call
#define codex_agent_skills_install \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_install), \
        ::codex_agent::detail::NativeSymbol::s648>::call
#define codex_agent_skills_is_available \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_is_available), \
        ::codex_agent::detail::NativeSymbol::s649>::call
#define codex_agent_skills_list \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_list), \
        ::codex_agent::detail::NativeSymbol::s650>::call
#define codex_agent_skills_read \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_read), \
        ::codex_agent::detail::NativeSymbol::s651>::call
#define codex_agent_skills_release \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_release), \
        ::codex_agent::detail::NativeSymbol::s652>::call
#define codex_agent_skills_retain \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_retain), \
        ::codex_agent::detail::NativeSymbol::s653>::call
#define codex_agent_skills_uninstall \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_skills_uninstall), \
        ::codex_agent::detail::NativeSymbol::s654>::call
#define codex_agent_snapshot_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_snapshot_destroy), \
        ::codex_agent::detail::NativeSymbol::s655>::call
#define codex_agent_state_boolean_value \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_state_boolean_value), \
        ::codex_agent::detail::NativeSymbol::s656>::call
#define codex_agent_subscription_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_subscription_destroy), \
        ::codex_agent::detail::NativeSymbol::s657>::call
#define codex_agent_turn_progress_commentary_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_commentary_copy), \
        ::codex_agent::detail::NativeSymbol::s658>::call
#define codex_agent_turn_progress_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_destroy), \
        ::codex_agent::detail::NativeSymbol::s659>::call
#define codex_agent_turn_progress_has_plan_progress \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_has_plan_progress), \
        ::codex_agent::detail::NativeSymbol::s660>::call
#define codex_agent_turn_progress_hook_activities_count \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_hook_activities_count), \
        ::codex_agent::detail::NativeSymbol::s661>::call
#define codex_agent_turn_progress_hook_activity_at \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_hook_activity_at), \
        ::codex_agent::detail::NativeSymbol::s662>::call
#define codex_agent_turn_progress_is_truncated \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_is_truncated), \
        ::codex_agent::detail::NativeSymbol::s663>::call
#define codex_agent_turn_progress_plan_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_plan_copy), \
        ::codex_agent::detail::NativeSymbol::s664>::call
#define codex_agent_turn_progress_plan_progress \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_plan_progress), \
        ::codex_agent::detail::NativeSymbol::s665>::call
#define codex_agent_turn_progress_reasoning_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_reasoning_copy), \
        ::codex_agent::detail::NativeSymbol::s666>::call
#define codex_agent_turn_progress_shell_exit_code \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_shell_exit_code), \
        ::codex_agent::detail::NativeSymbol::s667>::call
#define codex_agent_turn_progress_shell_output_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_shell_output_copy), \
        ::codex_agent::detail::NativeSymbol::s668>::call
#define codex_agent_turn_progress_text_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_text_copy), \
        ::codex_agent::detail::NativeSymbol::s669>::call
#define codex_agent_turn_progress_work_activity \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_progress_work_activity), \
        ::codex_agent::detail::NativeSymbol::s670>::call
#define codex_agent_turn_request_create \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_request_create), \
        ::codex_agent::detail::NativeSymbol::s671>::call
#define codex_agent_turn_request_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_turn_request_destroy), \
        ::codex_agent::detail::NativeSymbol::s672>::call
#define codex_agent_workspace_destroy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_workspace_destroy), \
        ::codex_agent::detail::NativeSymbol::s673>::call
#define codex_agent_workspace_display_name_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_workspace_display_name_copy), \
        ::codex_agent::detail::NativeSymbol::s674>::call
#define codex_agent_workspace_path_copy \
    ::codex_agent::detail::NativeEntry<decltype(&::codex_agent_workspace_path_copy), \
        ::codex_agent::detail::NativeSymbol::s675>::call
#endif
