#pragma once

namespace codex_agent {
namespace detail {

template <typename Copy>
inline std::string leaf_string(Copy copy) {
    return copy_string([&](std::uint8_t* buffer, std::size_t capacity,
                           std::size_t* required) {
        return copy(buffer, capacity, required);
    });
}

template <typename Has, typename Copy>
inline std::optional<std::string> leaf_optional_string(Has has, Copy copy) {
    std::int32_t present = 0;
    check(has(&present));
    if (present == 0) return std::nullopt;
    return leaf_string(copy);
}

template <typename Count, typename Copy>
inline std::vector<std::string> leaf_strings(Count count_fn, Copy copy_fn) {
    std::size_t count = 0;
    check(count_fn(&count));
    std::vector<std::string> result;
    result.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        result.push_back(leaf_string([&](auto* buffer, auto capacity,
                                         auto* required) {
            return copy_fn(index, buffer, capacity, required);
        }));
    }
    return result;
}

inline ServiceTier read_service_tier(
    const Context& context, codex_agent_service_tier_t* tier) {
    return {
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_service_tier_id_copy(
                context->raw, tier, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_service_tier_name_copy(
                context->raw, tier, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_service_tier_description_copy(
                context->raw, tier, b, n, r);
        }),
    };
}

inline Model read_model(const Context& context, codex_agent_model_t* model) {
    Model result;
    result.id = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_model_id_copy(context->raw, model, b, n, r);
    });
    result.display_name = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_model_display_name_copy(
            context->raw, model, b, n, r);
    });
    result.description = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_model_description_copy(
            context->raw, model, b, n, r);
    });
    result.supported_efforts = leaf_strings(
        [&](auto* count) {
            return codex_agent_model_supported_efforts_count(
                context->raw, model, count);
        },
        [&](auto index, auto* b, auto n, auto* r) {
            return codex_agent_model_supported_effort_copy_at(
                context->raw, model, index, b, n, r);
        });
    result.default_effort = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_model_default_effort_copy(
            context->raw, model, b, n, r);
    });
    std::int32_t flag = 0;
    check(codex_agent_model_is_default(context->raw, model, &flag));
    result.is_default = flag != 0;
    std::size_t tier_count = 0;
    check(codex_agent_model_service_tiers_count(
        context->raw, model, &tier_count));
    result.service_tiers.reserve(tier_count);
    for (std::size_t index = 0; index < tier_count; ++index) {
        codex_agent_service_tier_t* raw = nullptr;
        check(codex_agent_model_service_tier_at(
            context->raw, model, index, &raw));
        result.service_tiers.push_back(read_owned<
            codex_agent_service_tier_t, codex_agent_service_tier_destroy>(
            context, raw, read_service_tier));
    }
    result.default_service_tier = leaf_optional_string(
        [&](auto* present) {
            return codex_agent_model_has_default_service_tier(
                context->raw, model, present);
        },
        [&](auto* b, auto n, auto* r) {
            return codex_agent_model_default_service_tier_copy(
                context->raw, model, b, n, r);
        });
    return result;
}

inline ModelHandle make_model(const Context& context, const Model& model) {
    const auto id = string_view(model.id);
    const auto name = string_view(model.display_name);
    const auto description = string_view(model.description);
    const auto default_effort = string_view(model.default_effort);
    const auto default_tier = string_view(model.default_service_tier.value_or(""));
    std::vector<codex_agent_string_view_t> efforts;
    for (const auto& effort : model.supported_efforts) {
        efforts.push_back(string_view(effort));
    }
    std::vector<ServiceTierHandle> tiers;
    std::vector<codex_agent_service_tier_t*> raw_tiers;
    for (const auto& tier : model.service_tiers) {
        const auto tier_id = string_view(tier.id);
        const auto tier_name = string_view(tier.name);
        const auto tier_description = string_view(tier.description);
        tiers.push_back(make_sync_handle<
            codex_agent_service_tier_t, codex_agent_service_tier_destroy>(
            context, [&](auto** out) {
                return codex_agent_service_tier_create(
                    context->raw, &tier_id, &tier_name, &tier_description, out);
            }));
        raw_tiers.push_back(tiers.back().get());
    }
    return make_sync_handle<codex_agent_model_t, codex_agent_model_destroy>(
        context, [&](auto** out) {
            return codex_agent_model_create(
                context->raw, &id, &name, &description,
                efforts.empty() ? nullptr : efforts.data(), efforts.size(),
                &default_effort, model.is_default ? 1 : 0,
                raw_tiers.empty() ? nullptr : raw_tiers.data(),
                raw_tiers.size(), model.default_service_tier ? 1 : 0,
                &default_tier, out);
        });
}

inline Skill read_skill(const Context& context, codex_agent_skill_t* skill) {
    const auto text = [&](auto copy) {
        return leaf_string([&](auto* b, auto n, auto* r) {
            return copy(context->raw, skill, b, n, r);
        });
    };
    codex_agent_skill_scope_t scope = 0;
    codex_agent_resource_origin_t origin = 0;
    std::int32_t enabled = 0;
    std::int32_t removable = 0;
    check(codex_agent_skill_scope(context->raw, skill, &scope));
    check(codex_agent_skill_is_enabled(context->raw, skill, &enabled));
    check(codex_agent_skill_can_uninstall(context->raw, skill, &removable));
    check(codex_agent_skill_origin(context->raw, skill, &origin));
    return Skill(
        text(codex_agent_skill_name_copy),
        text(codex_agent_skill_display_name_copy),
        text(codex_agent_skill_description_copy),
        text(codex_agent_skill_path_copy), static_cast<SkillScope>(scope),
        enabled != 0,
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_skill_has_brand_color(
                    context->raw, skill, present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_skill_brand_color_copy(
                    context->raw, skill, b, n, r);
            }),
        leaf_strings(
            [&](auto* count) {
                return codex_agent_skill_dependencies_count(
                    context->raw, skill, count);
            },
            [&](auto index, auto* b, auto n, auto* r) {
                return codex_agent_skill_dependencies_copy_at(
                    context->raw, skill, index, b, n, r);
            }),
        removable != 0, static_cast<ResourceOrigin>(origin));
}

inline SkillHandle make_skill(const Context& context, const Skill& skill) {
    const auto name = string_view(skill.name);
    const auto display_name = string_view(skill.display_name);
    const auto description = string_view(skill.description);
    const auto path = string_view(skill.path);
    const auto brand = string_view(skill.brand_color.value_or(""));
    std::vector<codex_agent_string_view_t> dependencies;
    for (const auto& dependency : skill.dependencies) {
        dependencies.push_back(string_view(dependency));
    }
    return make_sync_handle<codex_agent_skill_t, codex_agent_skill_destroy>(
        context, [&](auto** out) {
            return codex_agent_skill_create(
                context->raw, &name, &display_name, &description, &path,
                static_cast<codex_agent_skill_scope_t>(skill.scope),
                skill.is_enabled ? 1 : 0, skill.brand_color ? 1 : 0, &brand,
                dependencies.empty() ? nullptr : dependencies.data(),
                dependencies.size(), skill.can_uninstall ? 1 : 0,
                1,
                static_cast<codex_agent_resource_origin_t>(skill.origin), out);
        });
}

inline SkillCatalog read_skill_catalog(
    const Context& context, codex_agent_skill_catalog_t* catalog) {
    std::size_t count = 0;
    check(codex_agent_skill_catalog_skills_count(
        context->raw, catalog, &count));
    SkillCatalog result;
    result.skills.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_skill_t* raw = nullptr;
        check(codex_agent_skill_catalog_skills_at(
            context->raw, catalog, index, &raw));
        result.skills.push_back(read_owned<
            codex_agent_skill_t, codex_agent_skill_destroy>(
            context, raw, read_skill));
    }
    result.errors = leaf_strings(
        [&](auto* out) {
            return codex_agent_skill_catalog_errors_count(
                context->raw, catalog, out);
        },
        [&](auto index, auto* b, auto n, auto* r) {
            return codex_agent_skill_catalog_errors_copy_at(
                context->raw, catalog, index, b, n, r);
        });
    return result;
}

inline SkillChunk read_skill_chunk(
    const Context& context, codex_agent_skill_chunk_t* chunk) {
    std::int32_t has_offset = 0;
    std::int64_t offset = 0;
    std::int64_t total = 0;
    check(codex_agent_skill_chunk_next_offset(
        context->raw, chunk, &has_offset, &offset));
    check(codex_agent_skill_chunk_total_bytes(context->raw, chunk, &total));
    return {
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_skill_chunk_content_copy(
                context->raw, chunk, b, n, r);
        }),
        has_offset != 0 ? std::optional<std::int64_t>(offset) : std::nullopt,
        total,
    };
}

inline Connector read_connector(
    const Context& context, codex_agent_connector_t* connector) {
    std::int32_t accessible = 0;
    std::int32_t enabled = 0;
    check(codex_agent_connector_is_accessible(
        context->raw, connector, &accessible));
    check(codex_agent_connector_is_enabled(
        context->raw, connector, &enabled));
    return {
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_connector_id_copy(
                context->raw, connector, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_connector_name_copy(
                context->raw, connector, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_connector_description_copy(
                context->raw, connector, b, n, r);
        }),
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_connector_has_install_url(
                    context->raw, connector, present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_connector_install_url_copy(
                    context->raw, connector, b, n, r);
            }),
        accessible != 0, enabled != 0,
        leaf_strings(
            [&](auto* count) {
                return codex_agent_connector_plugin_names_count(
                    context->raw, connector, count);
            },
            [&](auto index, auto* b, auto n, auto* r) {
                return codex_agent_connector_plugin_names_copy_at(
                    context->raw, connector, index, b, n, r);
            }),
    };
}

inline PluginReference read_plugin_reference(
    const Context& context, codex_agent_plugin_reference_t* reference) {
    return {
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_reference_id_copy(
                context->raw, reference, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_reference_name_copy(
                context->raw, reference, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_reference_marketplace_name_copy(
                context->raw, reference, b, n, r);
        }),
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_plugin_reference_has_marketplace_path(
                    context->raw, reference, present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_plugin_reference_marketplace_path_copy(
                    context->raw, reference, b, n, r);
            }),
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_plugin_reference_has_remote_plugin_id(
                    context->raw, reference, present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_plugin_reference_remote_plugin_id_copy(
                    context->raw, reference, b, n, r);
            }),
    };
}

inline PluginReferenceHandle make_plugin_reference(
    const Context& context, const PluginReference& reference) {
    const auto id = string_view(reference.id);
    const auto name = string_view(reference.name);
    const auto marketplace = string_view(reference.marketplace_name);
    const auto path = string_view(reference.marketplace_path.value_or(""));
    const auto remote = string_view(reference.remote_plugin_id.value_or(""));
    return make_sync_handle<
        codex_agent_plugin_reference_t,
        codex_agent_plugin_reference_destroy>(context, [&](auto** out) {
        return codex_agent_plugin_reference_create(
            context->raw, &id, &name, &marketplace,
            reference.marketplace_path ? 1 : 0, &path,
            reference.remote_plugin_id ? 1 : 0, &remote, out);
    });
}

inline PluginSkill read_plugin_skill(
    const Context& context, codex_agent_plugin_skill_t* skill) {
    std::int32_t enabled = 0;
    check(codex_agent_plugin_skill_is_enabled(
        context->raw, skill, &enabled));
    return {
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_skill_name_copy(
                context->raw, skill, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_skill_description_copy(
                context->raw, skill, b, n, r);
        }),
        enabled != 0,
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_plugin_skill_has_path(
                    context->raw, skill, present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_plugin_skill_path_copy(
                    context->raw, skill, b, n, r);
            }),
    };
}

inline PluginSummary read_plugin_summary(
    const Context& context, codex_agent_plugin_summary_t* summary) {
    codex_agent_plugin_reference_t* raw_reference = nullptr;
    check(codex_agent_plugin_summary_reference(
        context->raw, summary, &raw_reference));
    auto reference = read_owned<
        codex_agent_plugin_reference_t,
        codex_agent_plugin_reference_destroy>(
        context, raw_reference, read_plugin_reference);
    std::int32_t installed = 0;
    std::int32_t enabled = 0;
    std::int32_t available = 0;
    codex_agent_plugin_install_policy_t install_policy = 0;
    codex_agent_plugin_auth_policy_t auth_policy = 0;
    check(codex_agent_plugin_summary_is_installed(
        context->raw, summary, &installed));
    check(codex_agent_plugin_summary_is_enabled(
        context->raw, summary, &enabled));
    check(codex_agent_plugin_summary_install_policy(
        context->raw, summary, &install_policy));
    check(codex_agent_plugin_summary_auth_policy(
        context->raw, summary, &auth_policy));
    check(codex_agent_plugin_summary_is_available(
        context->raw, summary, &available));
    return {
        std::move(reference),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_summary_display_name_copy(
                context->raw, summary, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_summary_description_copy(
                context->raw, summary, b, n, r);
        }),
        installed != 0, enabled != 0,
        static_cast<PluginInstallPolicy>(install_policy),
        static_cast<PluginAuthPolicy>(auth_policy), available != 0,
        leaf_strings(
            [&](auto* count) {
                return codex_agent_plugin_summary_capabilities_count(
                    context->raw, summary, count);
            },
            [&](auto index, auto* b, auto n, auto* r) {
                return codex_agent_plugin_summary_capabilities_copy_at(
                    context->raw, summary, index, b, n, r);
            }),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_plugin_summary_has_brand_color(
                context->raw, summary, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_plugin_summary_brand_color_copy(
                context->raw, summary, b, n, r); }),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_plugin_summary_has_privacy_policy_url(
                context->raw, summary, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_plugin_summary_privacy_policy_url_copy(
                context->raw, summary, b, n, r); }),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_plugin_summary_has_terms_of_service_url(
                context->raw, summary, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_plugin_summary_terms_of_service_url_copy(
                context->raw, summary, b, n, r); }),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_plugin_summary_has_website_url(
                context->raw, summary, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_plugin_summary_website_url_copy(
                context->raw, summary, b, n, r); }),
    };
}

inline PluginCatalog read_plugin_catalog(
    const Context& context, codex_agent_plugin_catalog_t* catalog) {
    std::size_t count = 0;
    check(codex_agent_plugin_catalog_plugins_count(
        context->raw, catalog, &count));
    PluginCatalog result;
    result.plugins.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_plugin_summary_t* raw = nullptr;
        check(codex_agent_plugin_catalog_plugins_at(
            context->raw, catalog, index, &raw));
        result.plugins.push_back(read_owned<
            codex_agent_plugin_summary_t,
            codex_agent_plugin_summary_destroy>(
            context, raw, read_plugin_summary));
    }
    result.errors = leaf_strings(
        [&](auto* out) { return codex_agent_plugin_catalog_errors_count(
            context->raw, catalog, out); },
        [&](auto index, auto* b, auto n, auto* r) {
            return codex_agent_plugin_catalog_errors_copy_at(
                context->raw, catalog, index, b, n, r);
        });
    codex_agent_catalog_freshness_t freshness = 0;
    check(codex_agent_plugin_catalog_freshness(
        context->raw, catalog, &freshness));
    result.freshness = static_cast<CatalogFreshness>(freshness);
    return result;
}

inline PluginDetail read_plugin_detail(
    const Context& context, codex_agent_plugin_detail_t* detail) {
    codex_agent_plugin_summary_t* raw_summary = nullptr;
    check(codex_agent_plugin_detail_summary(
        context->raw, detail, &raw_summary));
    PluginDetail result{
        read_owned<codex_agent_plugin_summary_t,
                   codex_agent_plugin_summary_destroy>(
            context, raw_summary, read_plugin_summary),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_plugin_detail_description_copy(
                context->raw, detail, b, n, r);
        }), {}, {}, {}, 0};
    std::size_t count = 0;
    check(codex_agent_plugin_detail_skills_count(
        context->raw, detail, &count));
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_plugin_skill_t* raw = nullptr;
        check(codex_agent_plugin_detail_skills_at(
            context->raw, detail, index, &raw));
        result.skills.push_back(read_owned<
            codex_agent_plugin_skill_t, codex_agent_plugin_skill_destroy>(
            context, raw, read_plugin_skill));
    }
    check(codex_agent_plugin_detail_connectors_count(
        context->raw, detail, &count));
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_connector_t* raw = nullptr;
        check(codex_agent_plugin_detail_connectors_at(
            context->raw, detail, index, &raw));
        result.connectors.push_back(read_owned<
            codex_agent_connector_t, codex_agent_connector_destroy>(
            context, raw, read_connector));
    }
    result.mcp_servers = leaf_strings(
        [&](auto* out) { return codex_agent_plugin_detail_mcp_servers_count(
            context->raw, detail, out); },
        [&](auto index, auto* b, auto n, auto* r) {
            return codex_agent_plugin_detail_mcp_servers_copy_at(
                context->raw, detail, index, b, n, r);
        });
    check(codex_agent_plugin_detail_hook_count(
        context->raw, detail, &result.hook_count));
    return result;
}

inline PluginInstallResult read_plugin_install_result(
    const Context& context, codex_agent_plugin_install_result_t* install) {
    codex_agent_plugin_auth_policy_t policy = 0;
    check(codex_agent_plugin_install_result_auth_policy(
        context->raw, install, &policy));
    PluginInstallResult result{static_cast<PluginAuthPolicy>(policy), {},
                               std::nullopt};
    std::size_t count = 0;
    check(codex_agent_plugin_install_result_connectors_count(
        context->raw, install, &count));
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_connector_t* raw = nullptr;
        check(codex_agent_plugin_install_result_connectors_at(
            context->raw, install, index, &raw));
        result.connectors_needing_authentication.push_back(read_owned<
            codex_agent_connector_t, codex_agent_connector_destroy>(
            context, raw, read_connector));
    }
    result.message = leaf_optional_string(
        [&](auto* present) { return codex_agent_plugin_install_result_has_message(
            context->raw, install, present); },
        [&](auto* b, auto n, auto* r) { return codex_agent_plugin_install_result_message_copy(
            context->raw, install, b, n, r); });
    return result;
}

inline HookHandler read_hook_handler(
    const Context& context, codex_agent_hook_handler_t* handler) {
    codex_agent_hook_handler_kind_t kind = 0;
    check(codex_agent_hook_handler_kind(context->raw, handler, &kind));
    switch (kind) {
        case CODEX_AGENT_HOOK_HANDLER_KIND_AGENT:
            return hook_handler_agent;
        case CODEX_AGENT_HOOK_HANDLER_KIND_PROMPT:
            return hook_handler_prompt;
        case CODEX_AGENT_HOOK_HANDLER_KIND_COMMAND: {
            codex_agent_hook_handler_command_t* raw = nullptr;
            check(codex_agent_hook_handler_command(
                context->raw, handler, &raw));
            SyncHandle<
                codex_agent_hook_handler_command_t,
                codex_agent_hook_handler_command_destroy> owner(context, raw);
            std::int32_t is_async = 0;
            check(codex_agent_hook_handler_command_is_async(
                context->raw, owner.get(), &is_async));
            return HookHandlerCommand{
                leaf_string([&](auto* b, auto n, auto* r) {
                    return codex_agent_hook_handler_command_command_copy(
                        context->raw, owner.get(), b, n, r);
                }),
                is_async != 0};
        }
        case CODEX_AGENT_HOOK_HANDLER_KIND_MCP_TOOL: {
            codex_agent_hook_handler_mcp_tool_t* raw = nullptr;
            check(codex_agent_hook_handler_mcp_tool(
                context->raw, handler, &raw));
            SyncHandle<
                codex_agent_hook_handler_mcp_tool_t,
                codex_agent_hook_handler_mcp_tool_destroy> owner(context, raw);
            return HookHandlerMcpTool{
                leaf_string([&](auto* b, auto n, auto* r) {
                    return codex_agent_hook_handler_mcp_tool_server_copy(
                        context->raw, owner.get(), b, n, r);
                }),
                leaf_string([&](auto* b, auto n, auto* r) {
                    return codex_agent_hook_handler_mcp_tool_tool_copy(
                        context->raw, owner.get(), b, n, r);
                })};
        }
    }
    throw Error(Status::internal_error);
}

inline HookHandlerHandle make_hook_handler(
    const Context& context, const HookHandler& handler) {
    return std::visit(
        [&](const auto& value) -> HookHandlerHandle {
            using Value = std::decay_t<decltype(value)>;
            codex_agent_hook_handler_t* raw = nullptr;
            if constexpr (std::is_same_v<Value, HookHandlerAgent>) {
                auto concrete = make_sync_handle<
                    codex_agent_hook_handler_agent_t,
                    codex_agent_hook_handler_agent_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_hook_handler_agent_acquire(
                            context->raw, out);
                    });
                check(codex_agent_hook_handler_from_agent(
                    context->raw, concrete.get(), &raw));
            } else if constexpr (std::is_same_v<Value, HookHandlerPrompt>) {
                auto concrete = make_sync_handle<
                    codex_agent_hook_handler_prompt_t,
                    codex_agent_hook_handler_prompt_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_hook_handler_prompt_acquire(
                            context->raw, out);
                    });
                check(codex_agent_hook_handler_from_prompt(
                    context->raw, concrete.get(), &raw));
            } else if constexpr (std::is_same_v<Value, HookHandlerCommand>) {
                const auto command = string_view(value.command);
                auto concrete = make_sync_handle<
                    codex_agent_hook_handler_command_t,
                    codex_agent_hook_handler_command_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_hook_handler_command_create(
                            context->raw, &command, value.is_async ? 1 : 0,
                            out);
                    });
                check(codex_agent_hook_handler_from_command(
                    context->raw, concrete.get(), &raw));
            } else {
                const auto server = string_view(value.server);
                const auto tool = string_view(value.tool);
                auto concrete = make_sync_handle<
                    codex_agent_hook_handler_mcp_tool_t,
                    codex_agent_hook_handler_mcp_tool_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_hook_handler_mcp_tool_create(
                            context->raw, &server, &tool, out);
                    });
                check(codex_agent_hook_handler_from_mcp_tool(
                    context->raw, concrete.get(), &raw));
            }
            return {context, raw};
        },
        handler);
}

inline Hook read_hook(const Context& context, codex_agent_hook_t* hook) {
    codex_agent_hook_handler_t* raw_handler = nullptr;
    check(codex_agent_hook_handler(context->raw, hook, &raw_handler));
    HookHandlerHandle handler(context, raw_handler);
    std::int32_t enabled = 0;
    std::int32_t managed = 0;
    std::int32_t can_trust = 0;
    std::int32_t can_uninstall = 0;
    std::int64_t timeout = 0;
    codex_agent_hook_trust_status_t trust = 0;
    codex_agent_resource_origin_t origin = 0;
    check(codex_agent_hook_is_enabled(context->raw, hook, &enabled));
    check(codex_agent_hook_is_managed(context->raw, hook, &managed));
    check(codex_agent_hook_can_trust(context->raw, hook, &can_trust));
    check(codex_agent_hook_can_uninstall(
        context->raw, hook, &can_uninstall));
    check(codex_agent_hook_timeout_seconds(context->raw, hook, &timeout));
    check(codex_agent_hook_trust_status(context->raw, hook, &trust));
    check(codex_agent_hook_origin(context->raw, hook, &origin));
    return {
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_hook_key_copy(context->raw, hook, b, n, r); }),
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_hook_event_name_copy(context->raw, hook, b, n, r); }),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_hook_has_matcher(context->raw, hook, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_hook_matcher_copy(context->raw, hook, b, n, r); }),
        read_hook_handler(context, handler.get()), timeout,
        static_cast<HookTrustStatus>(trust),
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_hook_current_hash_copy(context->raw, hook, b, n, r); }),
        enabled != 0,
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_hook_source_copy(context->raw, hook, b, n, r); }),
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_hook_source_path_copy(context->raw, hook, b, n, r); }),
        static_cast<ResourceOrigin>(origin),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_hook_has_plugin_id(context->raw, hook, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_hook_plugin_id_copy(context->raw, hook, b, n, r); }),
        managed != 0, can_trust != 0, can_uninstall != 0,
        leaf_optional_string(
            [&](auto* p) { return codex_agent_hook_has_status_message(context->raw, hook, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_hook_status_message_copy(context->raw, hook, b, n, r); }),
    };
}

inline HookHandle make_hook(const Context& context, const Hook& hook) {
    const auto key = string_view(hook.key);
    const auto hash = string_view(hook.current_hash);
    const auto event = string_view(hook.event_name);
    const auto source = string_view(hook.source);
    const auto path = string_view(hook.source_path);
    const auto matcher = string_view(hook.matcher.value_or(""));
    const auto plugin = string_view(hook.plugin_id.value_or(""));
    const auto message = string_view(hook.status_message.value_or(""));
    auto handler = make_hook_handler(context, hook.handler);
    return make_sync_handle<codex_agent_hook_t, codex_agent_hook_destroy>(
        context, [&](auto** out) {
            return codex_agent_hook_create(
                context->raw, &key, &hash, hook.is_enabled ? 1 : 0, &event,
                handler.get(), hook.is_managed ? 1 : 0, &source, &path,
                hook.timeout_seconds,
                static_cast<codex_agent_hook_trust_status_t>(hook.trust_status),
                hook.matcher ? 1 : 0, &matcher, hook.plugin_id ? 1 : 0,
                &plugin, hook.status_message ? 1 : 0, &message, 1,
                static_cast<codex_agent_resource_origin_t>(hook.origin),
                hook.can_uninstall ? 1 : 0, out);
        });
}

inline HookCatalog read_hook_catalog(
    const Context& context, codex_agent_hook_catalog_t* catalog) {
    HookCatalog result;
    std::size_t count = 0;
    check(codex_agent_hook_catalog_hooks_count(
        context->raw, catalog, &count));
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_hook_t* raw = nullptr;
        check(codex_agent_hook_catalog_hooks_at(
            context->raw, catalog, index, &raw));
        result.hooks.push_back(read_owned<
            codex_agent_hook_t, codex_agent_hook_destroy>(
            context, raw, read_hook));
    }
    result.warnings = leaf_strings(
        [&](auto* out) { return codex_agent_hook_catalog_warnings_count(
            context->raw, catalog, out); },
        [&](auto index, auto* b, auto n, auto* r) {
            return codex_agent_hook_catalog_warnings_copy_at(
                context->raw, catalog, index, b, n, r);
        });
    result.errors = leaf_strings(
        [&](auto* out) { return codex_agent_hook_catalog_errors_count(
            context->raw, catalog, out); },
        [&](auto index, auto* b, auto n, auto* r) {
            return codex_agent_hook_catalog_errors_copy_at(
                context->raw, catalog, index, b, n, r);
        });
    return result;
}

template <typename Handle, typename Has, typename Count, typename Key,
          typename Value>
inline std::optional<std::map<std::string, std::string>> read_optional_map(
    Handle* handle, Has has, Count count_fn, Key key_fn, Value value_fn) {
    std::int32_t present = 0;
    check(has(&present));
    if (present == 0) return std::nullopt;
    std::size_t count = 0;
    check(count_fn(&count));
    std::map<std::string, std::string> result;
    for (std::size_t index = 0; index < count; ++index) {
        auto key = leaf_string([&](auto* b, auto n, auto* r) {
            return key_fn(index, b, n, r);
        });
        auto value = leaf_string([&](auto* b, auto n, auto* r) {
            return value_fn(index, b, n, r);
        });
        result.emplace(std::move(key), std::move(value));
    }
    (void)handle;
    return result;
}

inline McpEnvironmentVariable read_mcp_environment_variable(
    const Context& context, codex_agent_mcp_environment_variable_t* variable) {
    std::int32_t present = 0;
    codex_agent_mcp_environment_source_t source = 0;
    check(codex_agent_mcp_environment_variable_source(
        context->raw, variable, &present, &source));
    return McpEnvironmentVariable(
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_mcp_environment_variable_name_copy(
                context->raw, variable, b, n, r);
        }),
        present != 0
            ? std::optional<McpEnvironmentSource>(
                  static_cast<McpEnvironmentSource>(source))
            : std::nullopt);
}

inline McpTransport read_mcp_transport(
    const Context& context, codex_agent_mcp_transport_t* transport) {
    codex_agent_mcp_transport_kind_t kind = 0;
    check(codex_agent_mcp_transport_kind(context->raw, transport, &kind));
    if (kind == CODEX_AGENT_MCP_TRANSPORT_KIND_HTTP) {
        codex_agent_mcp_transport_http_t* raw = nullptr;
        check(codex_agent_mcp_transport_http(context->raw, transport, &raw));
        SyncHandle<
            codex_agent_mcp_transport_http_t,
            codex_agent_mcp_transport_http_destroy> http(context, raw);
        return McpHttpTransport(
            leaf_string([&](auto* b, auto n, auto* r) {
                return codex_agent_mcp_transport_http_url_copy(
                    context->raw, http.get(), b, n, r);
            }),
            leaf_optional_string(
                [&](auto* p) {
                    return codex_agent_mcp_transport_http_has_bearer_token_environment_variable(
                        context->raw, http.get(), p);
                },
                [&](auto* b, auto n, auto* r) {
                    return codex_agent_mcp_transport_http_bearer_token_environment_variable_copy(
                        context->raw, http.get(), b, n, r);
                }),
            read_optional_map(
                http.get(),
                [&](auto* p) { return codex_agent_mcp_transport_http_has_headers(context->raw, http.get(), p); },
                [&](auto* c) { return codex_agent_mcp_transport_http_headers_count(context->raw, http.get(), c); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_http_headers_key_copy_at(context->raw, http.get(), i, b, n, r); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_http_headers_value_copy_at(context->raw, http.get(), i, b, n, r); }),
            read_optional_map(
                http.get(),
                [&](auto* p) { return codex_agent_mcp_transport_http_has_environment_headers(context->raw, http.get(), p); },
                [&](auto* c) { return codex_agent_mcp_transport_http_environment_headers_count(context->raw, http.get(), c); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_http_environment_headers_key_copy_at(context->raw, http.get(), i, b, n, r); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_http_environment_headers_value_copy_at(context->raw, http.get(), i, b, n, r); }),
            leaf_optional_string(
                [&](auto* p) { return codex_agent_mcp_transport_http_has_headers_helper(context->raw, http.get(), p); },
                [&](auto* b, auto n, auto* r) { return codex_agent_mcp_transport_http_headers_helper_copy(context->raw, http.get(), b, n, r); }));
    }
    if (kind == CODEX_AGENT_MCP_TRANSPORT_KIND_STDIO) {
        codex_agent_mcp_transport_stdio_t* raw = nullptr;
        check(codex_agent_mcp_transport_stdio(context->raw, transport, &raw));
        SyncHandle<
            codex_agent_mcp_transport_stdio_t,
            codex_agent_mcp_transport_stdio_destroy> stdio(context, raw);
        std::size_t count = 0;
        check(codex_agent_mcp_transport_stdio_forwarded_environment_count(
            context->raw, stdio.get(), &count));
        std::vector<McpEnvironmentVariable> forwarded;
        for (std::size_t index = 0; index < count; ++index) {
            codex_agent_mcp_environment_variable_t* variable = nullptr;
            check(codex_agent_mcp_transport_stdio_forwarded_environment_at(
                context->raw, stdio.get(), index, &variable));
            forwarded.push_back(read_owned<
                codex_agent_mcp_environment_variable_t,
                codex_agent_mcp_environment_variable_destroy>(
                context, variable, read_mcp_environment_variable));
        }
        return McpStdioTransport(
            leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_mcp_transport_stdio_command_copy(context->raw, stdio.get(), b, n, r); }),
            leaf_strings(
                [&](auto* c) { return codex_agent_mcp_transport_stdio_arguments_count(context->raw, stdio.get(), c); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_stdio_argument_copy_at(context->raw, stdio.get(), i, b, n, r); }),
            leaf_optional_string(
                [&](auto* p) { return codex_agent_mcp_transport_stdio_has_working_directory(context->raw, stdio.get(), p); },
                [&](auto* b, auto n, auto* r) { return codex_agent_mcp_transport_stdio_working_directory_copy(context->raw, stdio.get(), b, n, r); }),
            read_optional_map(
                stdio.get(),
                [&](auto* p) { return codex_agent_mcp_transport_stdio_has_environment(context->raw, stdio.get(), p); },
                [&](auto* c) { return codex_agent_mcp_transport_stdio_environment_count(context->raw, stdio.get(), c); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_stdio_environment_key_copy_at(context->raw, stdio.get(), i, b, n, r); },
                [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_transport_stdio_environment_value_copy_at(context->raw, stdio.get(), i, b, n, r); }),
            std::move(forwarded));
    }
    throw Error(Status::internal_error);
}

inline McpServerConfiguration read_mcp_configuration(
    const Context& context, codex_agent_mcp_server_configuration_t* config) {
    codex_agent_mcp_transport_t* raw_transport = nullptr;
    check(codex_agent_mcp_server_configuration_transport(
        context->raw, config, &raw_transport));
    SyncHandle<codex_agent_mcp_transport_t, codex_agent_mcp_transport_destroy>
        transport(context, raw_transport);
    std::int32_t has_auth = 0;
    codex_agent_mcp_authentication_t auth = 0;
    std::int32_t enabled = 0;
    std::int32_t required = 0;
    std::int32_t parallel = 0;
    check(codex_agent_mcp_server_configuration_authentication(
        context->raw, config, &has_auth, &auth));
    check(codex_agent_mcp_server_configuration_is_enabled(
        context->raw, config, &enabled));
    check(codex_agent_mcp_server_configuration_is_required(
        context->raw, config, &required));
    check(codex_agent_mcp_server_configuration_supports_parallel_tool_calls(
        context->raw, config, &parallel));
    const auto optional_double = [&](auto call) -> std::optional<double> {
        std::int32_t present = 0;
        double value = 0;
        check(call(&present, &value));
        return present != 0 ? std::optional<double>(value) : std::nullopt;
    };
    std::optional<std::vector<McpToolExposureSurface>> omit;
    std::int32_t has_omit = 0;
    check(codex_agent_mcp_server_configuration_has_omit_tools_from(
        context->raw, config, &has_omit));
    if (has_omit != 0) {
        std::size_t count = 0;
        check(codex_agent_mcp_server_configuration_omit_tools_from_count(
            context->raw, config, &count));
        omit.emplace();
        for (std::size_t index = 0; index < count; ++index) {
            codex_agent_mcp_tool_exposure_surface_t value = 0;
            check(codex_agent_mcp_server_configuration_omit_tools_from_at(
                context->raw, config, index, &value));
            omit->push_back(static_cast<McpToolExposureSurface>(value));
        }
    }
    const auto optional_strings = [&](auto has, auto count, auto copy)
        -> std::optional<std::vector<std::string>> {
        std::int32_t present = 0;
        check(has(&present));
        if (present == 0) return std::nullopt;
        return leaf_strings(count, copy);
    };
    std::int32_t has_default_approval = 0;
    codex_agent_mcp_tool_approval_t default_approval = 0;
    check(codex_agent_mcp_server_configuration_default_tool_approval(
        context->raw, config, &has_default_approval, &default_approval));
    std::optional<McpOauthConfiguration> oauth;
    std::int32_t has_oauth = 0;
    check(codex_agent_mcp_server_configuration_has_oauth(
        context->raw, config, &has_oauth));
    if (has_oauth != 0) {
        codex_agent_mcp_oauth_configuration_t* raw = nullptr;
        check(codex_agent_mcp_server_configuration_oauth(
            context->raw, config, &raw));
        SyncHandle<
            codex_agent_mcp_oauth_configuration_t,
            codex_agent_mcp_oauth_configuration_destroy> owner(context, raw);
        std::int32_t has_port = 0;
        std::int32_t port = 0;
        check(codex_agent_mcp_oauth_configuration_callback_port(
            context->raw, owner.get(), &has_port, &port));
        oauth.emplace(
            leaf_optional_string(
                [&](auto* p) { return codex_agent_mcp_oauth_configuration_has_client_id(context->raw, owner.get(), p); },
                [&](auto* b, auto n, auto* r) { return codex_agent_mcp_oauth_configuration_client_id_copy(context->raw, owner.get(), b, n, r); }),
            has_port != 0 ? std::optional<std::int32_t>(port) : std::nullopt);
    }
    std::map<std::string, McpToolConfiguration> tools;
    std::size_t tool_count = 0;
    check(codex_agent_mcp_server_configuration_tools_count(
        context->raw, config, &tool_count));
    for (std::size_t index = 0; index < tool_count; ++index) {
        auto key = leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_tools_key_copy_at(context->raw, config, index, b, n, r); });
        codex_agent_mcp_tool_configuration_t* raw = nullptr;
        check(codex_agent_mcp_server_configuration_tools_value_at(
            context->raw, config, index, &raw));
        SyncHandle<
            codex_agent_mcp_tool_configuration_t,
            codex_agent_mcp_tool_configuration_destroy> owner(context, raw);
        std::int32_t present = 0;
        codex_agent_mcp_tool_approval_t approval = 0;
        check(codex_agent_mcp_tool_configuration_approval(
            context->raw, owner.get(), &present, &approval));
        tools.emplace(std::move(key), McpToolConfiguration{
            present != 0 ? std::optional<McpToolApproval>(static_cast<McpToolApproval>(approval)) : std::nullopt});
    }
    return McpServerConfiguration(
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_name_copy(context->raw, config, b, n, r); }),
        read_mcp_transport(context, transport.get()),
        has_auth != 0 ? std::optional<McpAuthentication>(static_cast<McpAuthentication>(auth)) : std::nullopt,
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_environment_id_copy(context->raw, config, b, n, r); }),
        enabled != 0, required != 0, parallel != 0, std::move(omit),
        optional_double([&](auto* p, auto* v) { return codex_agent_mcp_server_configuration_startup_timeout_seconds(context->raw, config, p, v); }),
        optional_double([&](auto* p, auto* v) { return codex_agent_mcp_server_configuration_tool_timeout_seconds(context->raw, config, p, v); }),
        has_default_approval != 0 ? std::optional<McpToolApproval>(static_cast<McpToolApproval>(default_approval)) : std::nullopt,
        optional_strings(
            [&](auto* p) { return codex_agent_mcp_server_configuration_has_enabled_tools(context->raw, config, p); },
            [&](auto* c) { return codex_agent_mcp_server_configuration_enabled_tools_count(context->raw, config, c); },
            [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_enabled_tool_copy_at(context->raw, config, i, b, n, r); }),
        optional_strings(
            [&](auto* p) { return codex_agent_mcp_server_configuration_has_disabled_tools(context->raw, config, p); },
            [&](auto* c) { return codex_agent_mcp_server_configuration_disabled_tools_count(context->raw, config, c); },
            [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_disabled_tool_copy_at(context->raw, config, i, b, n, r); }),
        optional_strings(
            [&](auto* p) { return codex_agent_mcp_server_configuration_has_scopes(context->raw, config, p); },
            [&](auto* c) { return codex_agent_mcp_server_configuration_scopes_count(context->raw, config, c); },
            [&](auto i, auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_scope_copy_at(context->raw, config, i, b, n, r); }),
        std::move(oauth),
        leaf_optional_string(
            [&](auto* p) { return codex_agent_mcp_server_configuration_has_oauth_resource(context->raw, config, p); },
            [&](auto* b, auto n, auto* r) { return codex_agent_mcp_server_configuration_oauth_resource_copy(context->raw, config, b, n, r); }),
        std::move(tools));
}

inline McpServer read_mcp_server(
    const Context& context, codex_agent_mcp_server_t* server) {
    codex_agent_mcp_auth_status_t auth = 0;
    codex_agent_resource_origin_t origin = 0;
    std::int32_t removable = 0;
    std::int32_t has_config = 0;
    check(codex_agent_mcp_server_auth_status(context->raw, server, &auth));
    check(codex_agent_mcp_server_origin(context->raw, server, &origin));
    check(codex_agent_mcp_server_can_remove(context->raw, server, &removable));
    check(codex_agent_mcp_server_has_configuration(
        context->raw, server, &has_config));
    std::optional<McpServerConfiguration> config;
    if (has_config != 0) {
        codex_agent_mcp_server_configuration_t* raw = nullptr;
        check(codex_agent_mcp_server_configuration(
            context->raw, server, &raw));
        config = read_owned<
            codex_agent_mcp_server_configuration_t,
            codex_agent_mcp_server_configuration_destroy>(
            context, raw, read_mcp_configuration);
    }
    return McpServer(
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_mcp_server_name_copy(context->raw, server, b, n, r); }),
        leaf_string([&](auto* b, auto n, auto* r) { return codex_agent_mcp_server_display_name_copy(context->raw, server, b, n, r); }),
        static_cast<McpAuthStatus>(auth), std::move(config),
        static_cast<ResourceOrigin>(origin), removable != 0);
}

inline auto mcp_transport_views(
    const std::map<std::string, std::string>& values) {
    std::pair<std::vector<codex_agent_string_view_t>,
              std::vector<codex_agent_string_view_t>> result;
    for (const auto& [key, value] : values) {
        result.first.push_back(string_view(key));
        result.second.push_back(string_view(value));
    }
    return result;
}

inline SyncHandle<codex_agent_mcp_transport_t, codex_agent_mcp_transport_destroy>
make_mcp_transport(const Context& context, const McpTransport& transport) {
    return std::visit(
        [&](const auto& value) {
            using Value = std::decay_t<decltype(value)>;
            codex_agent_mcp_transport_t* raw = nullptr;
            if constexpr (std::is_same_v<Value, McpHttpTransport>) {
                const auto url = string_view(value.url);
                const auto bearer = string_view(value.bearer_token_environment_variable.value_or(""));
                const auto helper = string_view(value.headers_helper.value_or(""));
                auto headers = mcp_transport_views(value.headers.value_or(std::map<std::string, std::string>{}));
                auto environment = mcp_transport_views(value.environment_headers.value_or(std::map<std::string, std::string>{}));
                auto http = make_sync_handle<
                    codex_agent_mcp_transport_http_t,
                    codex_agent_mcp_transport_http_destroy>(context, [&](auto** out) {
                    return codex_agent_mcp_transport_http_create(
                        context->raw, &url,
                        value.bearer_token_environment_variable ? 1 : 0, &bearer,
                        value.headers ? 1 : 0,
                        headers.first.empty() ? nullptr : headers.first.data(),
                        headers.second.empty() ? nullptr : headers.second.data(),
                        headers.first.size(), value.environment_headers ? 1 : 0,
                        environment.first.empty() ? nullptr : environment.first.data(),
                        environment.second.empty() ? nullptr : environment.second.data(),
                        environment.first.size(), value.headers_helper ? 1 : 0,
                        &helper, out);
                });
                check(codex_agent_mcp_transport_from_http(
                    context->raw, http.get(), &raw));
            } else {
                const auto command = string_view(value.command);
                std::vector<codex_agent_string_view_t> arguments;
                for (const auto& item : value.arguments) arguments.push_back(string_view(item));
                const auto directory = string_view(value.working_directory.value_or(""));
                auto environment = mcp_transport_views(value.environment.value_or(std::map<std::string, std::string>{}));
                std::vector<SyncHandle<
                    codex_agent_mcp_environment_variable_t,
                    codex_agent_mcp_environment_variable_destroy>> forwarded;
                std::vector<codex_agent_mcp_environment_variable_t*> raw_forwarded;
                for (const auto& item : value.forwarded_environment) {
                    const auto name = string_view(item.name);
                    forwarded.push_back(make_sync_handle<
                        codex_agent_mcp_environment_variable_t,
                        codex_agent_mcp_environment_variable_destroy>(context, [&](auto** out) {
                        return codex_agent_mcp_environment_variable_create(
                            context->raw, &name, item.source ? 1 : 0,
                            static_cast<codex_agent_mcp_environment_source_t>(item.source.value_or(McpEnvironmentSource::local)), out);
                    }));
                    raw_forwarded.push_back(forwarded.back().get());
                }
                auto stdio = make_sync_handle<
                    codex_agent_mcp_transport_stdio_t,
                    codex_agent_mcp_transport_stdio_destroy>(context, [&](auto** out) {
                    return codex_agent_mcp_transport_stdio_create(
                        context->raw, &command,
                        arguments.empty() ? nullptr : arguments.data(), arguments.size(),
                        value.working_directory ? 1 : 0, &directory,
                        value.environment ? 1 : 0,
                        environment.first.empty() ? nullptr : environment.first.data(),
                        environment.second.empty() ? nullptr : environment.second.data(),
                        environment.first.size(),
                        raw_forwarded.empty() ? nullptr : raw_forwarded.data(),
                        raw_forwarded.size(), out);
                });
                check(codex_agent_mcp_transport_from_stdio(
                    context->raw, stdio.get(), &raw));
            }
            return SyncHandle<codex_agent_mcp_transport_t,
                              codex_agent_mcp_transport_destroy>(context, raw);
        },
        transport);
}

inline McpServerConfigurationHandle make_mcp_configuration(
    const Context& context, const McpServerConfiguration& config) {
    auto transport = make_mcp_transport(context, config.transport);
    const auto name = string_view(config.name);
    const auto environment = string_view(config.environment_id);
    const auto oauth_resource = string_view(config.oauth_resource.value_or(""));
    const auto views = [](const std::optional<std::vector<std::string>>& values) {
        std::vector<codex_agent_string_view_t> result;
        if (values) {
            for (const auto& value : *values) result.push_back(string_view(value));
        }
        return result;
    };
    auto enabled = views(config.enabled_tools);
    auto disabled = views(config.disabled_tools);
    auto scopes = views(config.scopes);
    std::vector<codex_agent_mcp_tool_exposure_surface_t> omit;
    if (config.omit_tools_from) {
        for (const auto value : *config.omit_tools_from) {
            omit.push_back(static_cast<codex_agent_mcp_tool_exposure_surface_t>(value));
        }
    }
    std::optional<SyncHandle<
        codex_agent_mcp_oauth_configuration_t,
        codex_agent_mcp_oauth_configuration_destroy>> oauth;
    if (config.oauth) {
        const auto client_id = string_view(config.oauth->client_id.value_or(""));
        oauth.emplace(make_sync_handle<
            codex_agent_mcp_oauth_configuration_t,
            codex_agent_mcp_oauth_configuration_destroy>(context, [&](auto** out) {
            return codex_agent_mcp_oauth_configuration_create(
                context->raw, config.oauth->client_id ? 1 : 0, &client_id,
                config.oauth->callback_port ? 1 : 0,
                config.oauth->callback_port.value_or(0), out);
        }));
    }
    std::vector<codex_agent_string_view_t> tool_keys;
    std::vector<SyncHandle<
        codex_agent_mcp_tool_configuration_t,
        codex_agent_mcp_tool_configuration_destroy>> tools;
    std::vector<codex_agent_mcp_tool_configuration_t*> raw_tools;
    for (const auto& [key, value] : config.tools) {
        tool_keys.push_back(string_view(key));
        tools.push_back(make_sync_handle<
            codex_agent_mcp_tool_configuration_t,
            codex_agent_mcp_tool_configuration_destroy>(context, [&](auto** out) {
            return codex_agent_mcp_tool_configuration_create(
                context->raw, value.approval ? 1 : 0,
                static_cast<codex_agent_mcp_tool_approval_t>(
                    value.approval.value_or(McpToolApproval::auto_)), out);
        }));
        raw_tools.push_back(tools.back().get());
    }
    return make_sync_handle<
        codex_agent_mcp_server_configuration_t,
        codex_agent_mcp_server_configuration_destroy>(context, [&](auto** out) {
        return codex_agent_mcp_server_configuration_create(
            context->raw, &name, transport.get(), config.authentication ? 1 : 0,
            static_cast<codex_agent_mcp_authentication_t>(
                config.authentication.value_or(McpAuthentication::oauth)),
            &environment, config.is_enabled ? 1 : 0,
            config.is_required ? 1 : 0,
            config.supports_parallel_tool_calls ? 1 : 0,
            config.omit_tools_from ? 1 : 0,
            omit.empty() ? nullptr : omit.data(), omit.size(),
            config.startup_timeout_seconds ? 1 : 0,
            config.startup_timeout_seconds.value_or(0),
            config.tool_timeout_seconds ? 1 : 0,
            config.tool_timeout_seconds.value_or(0),
            config.default_tool_approval ? 1 : 0,
            static_cast<codex_agent_mcp_tool_approval_t>(
                config.default_tool_approval.value_or(McpToolApproval::auto_)),
            config.enabled_tools ? 1 : 0,
            enabled.empty() ? nullptr : enabled.data(), enabled.size(),
            config.disabled_tools ? 1 : 0,
            disabled.empty() ? nullptr : disabled.data(), disabled.size(),
            config.scopes ? 1 : 0,
            scopes.empty() ? nullptr : scopes.data(), scopes.size(),
            config.oauth ? 1 : 0, oauth ? oauth->get() : nullptr,
            config.oauth_resource ? 1 : 0, &oauth_resource,
            tool_keys.empty() ? nullptr : tool_keys.data(),
            raw_tools.empty() ? nullptr : raw_tools.data(), raw_tools.size(),
            out);
    });
}

inline McpServerHandle make_mcp_server(
    const Context& context, const McpServer& server) {
    const auto name = string_view(server.name);
    const auto display_name = string_view(server.display_name);
    std::optional<McpServerConfigurationHandle> config;
    if (server.configuration) {
        config.emplace(make_mcp_configuration(context, *server.configuration));
    }
    return make_sync_handle<
        codex_agent_mcp_server_t, codex_agent_mcp_server_destroy>(
        context, [&](auto** out) {
            return codex_agent_mcp_server_create(
                context->raw, &name, &display_name,
                static_cast<codex_agent_mcp_auth_status_t>(server.auth_status),
                config ? config->get() : nullptr,
                static_cast<codex_agent_resource_origin_t>(server.origin),
                server.can_remove ? 1 : 0, out);
        });
}

inline AuthenticationState read_authentication_state(
    const Context& context, codex_agent_snapshot_t* snapshot) {
    codex_agent_authentication_state_t* raw = nullptr;
    check(codex_agent_authentication_state_value(
        context->raw, snapshot, &raw));
    AuthenticationStateHandle state(context, raw);
    codex_agent_authentication_status_t status = 0;
    check(codex_agent_authentication_state_status(
        context->raw, state.get(), &status));
    const auto url = [&](auto has, auto get,
                         AuthorizationPurpose purpose)
        -> std::optional<AuthorizationUrl> {
        std::int32_t present = 0;
        check(has(context->raw, state.get(), &present));
        if (present == 0) return std::nullopt;
        codex_agent_authorization_url_t* raw_url = nullptr;
        check(get(context->raw, state.get(), &raw_url));
        AuthorizationUrlHandle owner(context, raw_url);
        return read_authorization_url(context, owner, purpose);
    };
    AuthenticationState result{
        static_cast<AuthenticationStatus>(status),
        url(codex_agent_authentication_state_has_pending_sign_in_url,
            codex_agent_authentication_state_pending_sign_in_url,
            AuthorizationPurpose::chat_gpt),
        url(codex_agent_authentication_state_has_device_verification_url,
            codex_agent_authentication_state_device_verification_url,
            AuthorizationPurpose::chat_gpt),
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_authentication_state_has_device_user_code(
                    context->raw, state.get(), present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_authentication_state_device_user_code_copy(
                    context->raw, state.get(), b, n, r);
            }),
        std::nullopt,
    };
    std::int32_t has_failure = 0;
    check(codex_agent_authentication_state_has_failure(
        context->raw, state.get(), &has_failure));
    if (has_failure != 0) {
        codex_agent_failure_t* failure = nullptr;
        check(codex_agent_authentication_state_failure(
            context->raw, state.get(), &failure));
        try {
            result.failure = read_failure(context, failure);
            check(codex_agent_failure_release(context->raw, &failure));
        } catch (...) {
            if (failure != nullptr) {
                (void)codex_agent_failure_release(context->raw, &failure);
            }
            throw;
        }
    }
    return result;
}

inline IntegrationValue read_integration(
    const Context& context, codex_agent_integration_t* integration) {
    codex_agent_integration_kind_t kind = 0;
    check(codex_agent_integration_kind(context->raw, integration, &kind));
    if (kind == CODEX_AGENT_INTEGRATION_KIND_CONNECTOR) {
        codex_agent_integration_connector_t* raw = nullptr;
        check(codex_agent_integration_connector(
            context->raw, integration, &raw));
        IntegrationConnectorHandle owner(context, raw);
        codex_agent_connector_t* raw_connector = nullptr;
        check(codex_agent_integration_connector_connector(
            context->raw, owner.get(), &raw_connector));
        auto connector = read_owned<
            codex_agent_connector_t, codex_agent_connector_destroy>(
            context, raw_connector, read_connector);
        ConnectorIntegration result;
        result.connector = std::move(connector);
        result.id = leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_integration_connector_id_copy(
                context->raw, owner.get(), b, n, r);
        });
        result.display_name = leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_integration_connector_display_name_copy(
                context->raw, owner.get(), b, n, r);
        });
        return result;
    }
    if (kind == CODEX_AGENT_INTEGRATION_KIND_MCP_SERVER) {
        codex_agent_integration_mcp_server_t* raw = nullptr;
        check(codex_agent_integration_mcp_server(
            context->raw, integration, &raw));
        IntegrationMcpServerHandle owner(context, raw);
        codex_agent_mcp_server_t* raw_server = nullptr;
        check(codex_agent_integration_mcp_server_server(
            context->raw, owner.get(), &raw_server));
        auto server = read_owned<
            codex_agent_mcp_server_t, codex_agent_mcp_server_destroy>(
            context, raw_server, read_mcp_server);
        auto id = leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_integration_mcp_server_id_copy(
                context->raw, owner.get(), b, n, r);
        });
        auto display_name = leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_integration_mcp_server_display_name_copy(
                context->raw, owner.get(), b, n, r);
        });
        return McpServerIntegration{
            Integration{std::move(id), std::move(display_name)},
            std::move(server)};
    }
    throw Error(Status::internal_error);
}

inline IntegrationHandle make_integration(
    const Context& context, const IntegrationValue& integration) {
    return std::visit(
        [&](const auto& value) -> IntegrationHandle {
            using Value = std::decay_t<decltype(value)>;
            codex_agent_integration_t* raw = nullptr;
            if constexpr (std::is_same_v<Value, ConnectorIntegration>) {
                const auto id = string_view(value.connector.id);
                const auto name = string_view(value.connector.name);
                const auto description = string_view(value.connector.description);
                const auto install_url = string_view(
                    value.connector.install_url.value_or(""));
                std::vector<codex_agent_string_view_t> plugins;
                for (const auto& plugin : value.connector.plugin_names) {
                    plugins.push_back(string_view(plugin));
                }
                auto connector = make_sync_handle<
                    codex_agent_connector_t, codex_agent_connector_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_connector_create(
                            context->raw, &id, &name, &description,
                            value.connector.install_url ? 1 : 0, &install_url,
                            value.connector.is_accessible ? 1 : 0,
                            value.connector.is_enabled ? 1 : 0,
                            plugins.empty() ? nullptr : plugins.data(),
                            plugins.size(), out);
                    });
                auto concrete = make_sync_handle<
                    codex_agent_integration_connector_t,
                    codex_agent_integration_connector_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_integration_connector_create(
                            context->raw, connector.get(), out);
                    });
                check(codex_agent_integration_from_connector(
                    context->raw, concrete.get(), &raw));
            } else {
                auto server = make_mcp_server(context, value.server);
                auto concrete = make_sync_handle<
                    codex_agent_integration_mcp_server_t,
                    codex_agent_integration_mcp_server_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_integration_mcp_server_create(
                            context->raw, server.get(), out);
                    });
                check(codex_agent_integration_from_mcp_server(
                    context->raw, concrete.get(), &raw));
            }
            return {context, raw};
        },
        integration);
}

inline IntegrationAuthorizationState read_integration_authorization_state(
    const Context& context, codex_agent_snapshot_t* snapshot) {
    codex_agent_integration_authorization_state_t* raw = nullptr;
    check(codex_agent_integration_authorization_state_value(
        context->raw, snapshot, &raw));
    IntegrationAuthorizationStateHandle state(context, raw);
    codex_agent_integration_authorization_status_t status = 0;
    check(codex_agent_integration_authorization_state_status(
        context->raw, state.get(), &status));
    IntegrationAuthorizationState result{
        static_cast<IntegrationAuthorizationStatus>(status), std::nullopt,
        std::nullopt};
    codex_agent_integration_t* target = nullptr;
    const auto target_status = codex_agent_integration_authorization_state_target(
        context->raw, state.get(), &target);
    if (target_status == CODEX_AGENT_STATUS_OK) {
        IntegrationHandle owner(context, target);
        result.target = read_integration(context, owner.get());
    } else if (target_status != CODEX_AGENT_STATUS_NOT_READY) {
        check(target_status);
    }
    codex_agent_failure_t* failure = nullptr;
    const auto failure_status =
        codex_agent_integration_authorization_state_failure(
            context->raw, state.get(), &failure);
    if (failure_status == CODEX_AGENT_STATUS_OK) {
        try {
            result.failure = read_failure(context, failure);
            check(codex_agent_failure_release(context->raw, &failure));
        } catch (...) {
            if (failure != nullptr) {
                (void)codex_agent_failure_release(context->raw, &failure);
            }
            throw;
        }
    } else if (failure_status != CODEX_AGENT_STATUS_NOT_READY) {
        check(failure_status);
    }
    return result;
}

inline std::optional<IntegrationValue> read_active_integration(
    const Context& context, codex_agent_snapshot_t* snapshot) {
    std::int32_t present = 0;
    check(codex_agent_integration_authorization_active_has_value(
        context->raw, snapshot, &present));
    if (present == 0) return std::nullopt;
    codex_agent_integration_t* raw = nullptr;
    check(codex_agent_integration_authorization_active_value(
        context->raw, snapshot, &raw));
    IntegrationHandle owner(context, raw);
    return read_integration(context, owner.get());
}

inline PendingApproval read_pending_approval(
    const Context& context,
    const std::shared_ptr<PendingApprovalHandle>& owner,
    const std::shared_ptr<InteractionsHandle>& interactions) {
    codex_agent_conversation_id_t* raw_id = nullptr;
    check(codex_agent_pending_approval_conversation_id(
        context->raw, owner->get(), &raw_id));
    ConversationIdHandle id(context, raw_id);
    auto request_id = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_pending_approval_request_id_copy(
            context->raw, owner->get(), b, n, r);
    });
    auto conversation_id = ConversationId(leaf_string(
        [&](auto* b, auto n, auto* r) {
            return codex_agent_conversation_id_value_copy(
                context->raw, id.get(), b, n, r);
        }));
    auto title = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_pending_approval_title_copy(
            context->raw, owner->get(), b, n, r);
    });
    auto details = leaf_string([&](auto* b, auto n, auto* r) {
        return codex_agent_pending_approval_details_copy(
            context->raw, owner->get(), b, n, r);
    });
    return PendingApproval{
        PendingInteraction{
            std::move(request_id), std::move(conversation_id),
            std::make_shared<LivePending>(LivePending{owner, interactions})},
        std::move(title), std::move(details)};
}

inline Elicitation read_native_elicitation(
    const Context& context, codex_agent_elicitation_t* elicitation) {
    codex_agent_conversation_id_t* raw_id = nullptr;
    check(codex_agent_elicitation_conversation_id(
        context->raw, elicitation, &raw_id));
    ConversationIdHandle id(context, raw_id);
    Elicitation result{
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_elicitation_request_id_copy(
                context->raw, elicitation, b, n, r);
        }),
        ConversationId(leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_conversation_id_value_copy(
                context->raw, id.get(), b, n, r);
        })),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_elicitation_server_name_copy(
                context->raw, elicitation, b, n, r);
        }),
        leaf_string([&](auto* b, auto n, auto* r) {
            return codex_agent_elicitation_message_copy(
                context->raw, elicitation, b, n, r);
        }),
        leaf_optional_string(
            [&](auto* present) {
                return codex_agent_elicitation_has_url(
                    context->raw, elicitation, present);
            },
            [&](auto* b, auto n, auto* r) {
                return codex_agent_elicitation_url_copy(
                    context->raw, elicitation, b, n, r);
            }),
        std::nullopt,
    };
    std::int32_t has_form = 0;
    check(codex_agent_elicitation_has_form(
        context->raw, elicitation, &has_form));
    if (has_form != 0) {
        std::size_t count = 0;
        check(codex_agent_elicitation_form_count(
            context->raw, elicitation, &count));
        std::vector<FormField> fields;
        fields.reserve(count);
        for (std::size_t index = 0; index < count; ++index) {
            codex_agent_form_field_t* raw_field = nullptr;
            check(codex_agent_elicitation_form_at(
                context->raw, elicitation, index, &raw_field));
            FormFieldHandle field(context, raw_field);
            codex_agent_form_field_type_t type = 0;
            std::int32_t required = 0;
            std::int32_t secret = 0;
            std::int32_t allows_other = 0;
            check(codex_agent_form_field_type(
                context->raw, field.get(), &type));
            check(codex_agent_form_field_is_required(
                context->raw, field.get(), &required));
            check(codex_agent_form_field_is_secret(
                context->raw, field.get(), &secret));
            check(codex_agent_form_field_allows_other(
                context->raw, field.get(), &allows_other));
            const auto optional_double = [&](auto read) {
                std::int32_t present = 0;
                double value = 0.0;
                check(read(&present, &value));
                return present == 0 ? std::optional<double>{}
                                    : std::optional<double>{value};
            };
            const auto optional_integer = [&](auto read) {
                std::int32_t present = 0;
                std::int64_t value = 0;
                check(read(&present, &value));
                return present == 0 ? std::optional<std::int64_t>{}
                                    : std::optional<std::int64_t>{value};
            };
            std::int32_t has_format = 0;
            codex_agent_form_string_format_t format = 0;
            check(codex_agent_form_field_format(
                context->raw, field.get(), &has_format, &format));
            std::int32_t has_default = 0;
            check(codex_agent_form_field_has_default_value(
                context->raw, field.get(), &has_default));
            std::optional<FormValue> default_value;
            if (has_default != 0) {
                codex_agent_form_value_t* raw_default = nullptr;
                check(codex_agent_form_field_default_value(
                    context->raw, field.get(), &raw_default));
                FormValueHandle owned_default(context, raw_default);
                default_value = read_form_value(context, owned_default.get());
            }
            std::size_t option_count = 0;
            check(codex_agent_form_field_options_count(
                context->raw, field.get(), &option_count));
            std::vector<FormOption> options;
            options.reserve(option_count);
            for (std::size_t option_index = 0;
                 option_index < option_count; ++option_index) {
                codex_agent_form_option_t* raw_option = nullptr;
                check(codex_agent_form_field_option_at(
                    context->raw, field.get(), option_index, &raw_option));
                FormOptionHandle option(context, raw_option);
                options.push_back(FormOption{
                    leaf_string([&](auto* b, auto n, auto* r) {
                        return codex_agent_form_option_value_copy(
                            context->raw, option.get(), b, n, r);
                    }),
                    leaf_string([&](auto* b, auto n, auto* r) {
                        return codex_agent_form_option_title_copy(
                            context->raw, option.get(), b, n, r);
                    }),
                    leaf_optional_string(
                        [&](auto* present) {
                            return codex_agent_form_option_has_description(
                                context->raw, option.get(), present);
                        },
                        [&](auto* b, auto n, auto* r) {
                            return codex_agent_form_option_description_copy(
                                context->raw, option.get(), b, n, r);
                        })});
            }
            FormField projected{
                leaf_string([&](auto* b, auto n, auto* r) {
                    return codex_agent_form_field_name_copy(
                        context->raw, field.get(), b, n, r);
                }),
                leaf_string([&](auto* b, auto n, auto* r) {
                    return codex_agent_form_field_title_copy(
                        context->raw, field.get(), b, n, r);
                }),
                leaf_optional_string(
                    [&](auto* present) {
                        return codex_agent_form_field_has_description(
                            context->raw, field.get(), present);
                    },
                    [&](auto* b, auto n, auto* r) {
                        return codex_agent_form_field_description_copy(
                            context->raw, field.get(), b, n, r);
                }),
                static_cast<FormFieldType>(type), required != 0, secret != 0,
                has_format == 0
                    ? std::optional<FormStringFormat>{}
                    : std::optional<FormStringFormat>{
                          static_cast<FormStringFormat>(format)},
                std::move(default_value),
                optional_double([&](auto* present, auto* value) {
                    return codex_agent_form_field_minimum(
                        context->raw, field.get(), present, value);
                }),
                optional_double([&](auto* present, auto* value) {
                    return codex_agent_form_field_maximum(
                        context->raw, field.get(), present, value);
                }),
                optional_integer([&](auto* present, auto* value) {
                    return codex_agent_form_field_minimum_length(
                        context->raw, field.get(), present, value);
                }),
                optional_integer([&](auto* present, auto* value) {
                    return codex_agent_form_field_maximum_length(
                        context->raw, field.get(), present, value);
                }),
                std::move(options), allows_other != 0,
                optional_integer([&](auto* present, auto* value) {
                    return codex_agent_form_field_minimum_selections(
                        context->raw, field.get(), present, value);
                }),
                optional_integer([&](auto* present, auto* value) {
                    return codex_agent_form_field_maximum_selections(
                        context->raw, field.get(), present, value);
                })};
            fields.push_back(std::move(projected));
        }
        result.form = std::move(fields);
    }
    return result;
}

inline PendingElicitation read_pending_elicitation(
    const Context& context,
    const std::shared_ptr<PendingElicitationHandle>& owner,
    const std::shared_ptr<InteractionsHandle>& interactions) {
    codex_agent_elicitation_t* raw = nullptr;
    check(codex_agent_pending_elicitation_elicitation(
        context->raw, owner->get(), &raw));
    ElicitationHandle elicitation(context, raw);
    auto projected = read_native_elicitation(context, elicitation.get());
    return PendingElicitation{
        PendingInteraction{
            projected.request_id, projected.conversation_id,
            std::make_shared<LivePending>(LivePending{owner, interactions})},
        std::move(projected)};
}

inline std::vector<PendingApproval> read_approvals(
    const Context& context, codex_agent_snapshot_t* snapshot,
    const std::shared_ptr<InteractionsHandle>& interactions) {
    std::size_t count = 0;
    check(codex_agent_interactions_approvals_count(
        context->raw, snapshot, &count));
    std::vector<PendingApproval> result;
    result.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_pending_approval_t* raw = nullptr;
        check(codex_agent_interactions_approvals_at(
            context->raw, snapshot, index, &raw));
        auto owner = std::make_shared<PendingApprovalHandle>(context, raw);
        result.push_back(read_pending_approval(context, owner, interactions));
    }
    return result;
}

inline std::vector<PendingElicitation> read_elicitations(
    const Context& context, codex_agent_snapshot_t* snapshot,
    const std::shared_ptr<InteractionsHandle>& interactions) {
    std::size_t count = 0;
    check(codex_agent_interactions_elicitations_count(
        context->raw, snapshot, &count));
    std::vector<PendingElicitation> result;
    result.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_pending_elicitation_t* raw = nullptr;
        check(codex_agent_interactions_elicitations_at(
            context->raw, snapshot, index, &raw));
        auto owner = std::make_shared<PendingElicitationHandle>(context, raw);
        result.push_back(read_pending_elicitation(context, owner, interactions));
    }
    return result;
}

inline InteractionState read_interaction_state(
    const Context& context, codex_agent_snapshot_t* snapshot,
    const std::shared_ptr<InteractionsHandle>& interactions) {
    codex_agent_interaction_state_t* raw = nullptr;
    check(codex_agent_interactions_state_value(
        context->raw, snapshot, &raw));
    InteractionStateHandle state(context, raw);
    InteractionState result;
    std::size_t count = 0;
    check(codex_agent_interaction_state_pending_count(
        context->raw, state.get(), &count));
    result.pending.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_pending_interaction_t* raw_pending = nullptr;
        check(codex_agent_interaction_state_pending_at(
            context->raw, state.get(), index, &raw_pending));
        PendingInteractionHandle pending(context, raw_pending);
        codex_agent_pending_interaction_kind_t kind = 0;
        check(codex_agent_pending_interaction_kind(
            context->raw, pending.get(), &kind));
        if (kind == CODEX_AGENT_PENDING_INTERACTION_KIND_APPROVAL) {
            codex_agent_pending_approval_t* raw_approval = nullptr;
            check(codex_agent_pending_interaction_approval(
                context->raw, pending.get(), &raw_approval));
            auto owner =
                std::make_shared<PendingApprovalHandle>(context, raw_approval);
            result.pending.emplace_back(
                read_pending_approval(context, owner, interactions));
        } else if (kind == CODEX_AGENT_PENDING_INTERACTION_KIND_ELICITATION) {
            codex_agent_pending_elicitation_t* raw_elicitation = nullptr;
            check(codex_agent_pending_interaction_elicitation(
                context->raw, pending.get(), &raw_elicitation));
            auto owner = std::make_shared<PendingElicitationHandle>(
                context, raw_elicitation);
            result.pending.emplace_back(
                read_pending_elicitation(context, owner, interactions));
        } else {
            throw Error(Status::internal_error);
        }
    }
    for (const auto& pending : result.pending) {
        const auto request_id = std::visit(
            [](const auto& item) { return string_view(item.request_id); },
            pending);
        std::int32_t contains = 0;
        check(codex_agent_interaction_state_resolving_request_ids_contains(
            context->raw, state.get(), &request_id, &contains));
        if (contains != 0) {
            result.resolving_request_ids.insert(
                std::visit([](const auto& item) { return item.request_id; },
                           pending));
        }
    }
    std::int32_t has_failure = 0;
    check(codex_agent_interaction_state_has_failure(
        context->raw, state.get(), &has_failure));
    if (has_failure != 0) {
        codex_agent_failure_t* failure = nullptr;
        check(codex_agent_interaction_state_failure(
            context->raw, state.get(), &failure));
        try {
            result.failure = read_failure(context, failure);
            check(codex_agent_failure_release(context->raw, &failure));
        } catch (...) {
            if (failure != nullptr) {
                (void)codex_agent_failure_release(context->raw, &failure);
            }
            throw;
        }
    }
    return result;
}

}  // namespace detail

inline AsyncOperation<void> Authentication::authenticate(
    ApiKeyAuthentication method) const {
    auto context = handle_.context();
    const auto value = detail::string_view(method.value);
    auto input = std::make_shared<detail::ApiKeyAuthenticationHandle>(
        detail::make_sync_handle<
            codex_agent_authentication_method_api_key_t,
            codex_agent_authentication_method_api_key_destroy>(
            context, [&](auto** out) {
                return codex_agent_authentication_method_api_key_create(
                    context->raw, &value, out);
            }));
    return detail::leaf_void_operation<
        codex_agent_authentication_t, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_authentication_authenticate_api_key(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline AsyncOperation<void> Authentication::authenticate(
    ChatGptBrowserAuthentication) const {
    auto context = handle_.context();
    auto input = std::make_shared<detail::BrowserAuthenticationHandle>(
        detail::make_sync_handle<
            codex_agent_authentication_method_chat_gpt_browser_t,
            codex_agent_authentication_method_chat_gpt_browser_destroy>(
            context, [&](auto** out) {
                return codex_agent_authentication_method_chat_gpt_browser_create(
                    context->raw, out);
            }));
    return detail::leaf_void_operation<
        codex_agent_authentication_t, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_authentication_authenticate_chat_gpt_browser(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline AsyncOperation<void> Authentication::authenticate(
    ChatGptDeviceCodeAuthentication) const {
    auto context = handle_.context();
    auto input = std::make_shared<detail::DeviceAuthenticationHandle>(
        detail::make_sync_handle<
            codex_agent_authentication_method_chat_gpt_device_code_t,
            codex_agent_authentication_method_chat_gpt_device_code_destroy>(
            context, [&](auto** out) {
                return
                    codex_agent_authentication_method_chat_gpt_device_code_create(
                        context->raw, out);
            }));
    return detail::leaf_void_operation<
        codex_agent_authentication_t, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return
                codex_agent_authentication_authenticate_chat_gpt_device_code(
                    context->raw, owner->get(), input->get(), callback,
                    user_data, out);
        });
}

inline AsyncOperation<void> Authentication::cancel() const {
    return detail::leaf_void_operation<
        codex_agent_authentication_t, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, [](const detail::Context& context, const auto& owner,
                    auto callback, void* user_data, auto** out) {
            return codex_agent_authentication_cancel(
                context->raw, owner->get(), callback, user_data, out);
        });
}

inline AsyncOperation<void> Authentication::sign_out() const {
    return detail::leaf_void_operation<
        codex_agent_authentication_t, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, [](const detail::Context& context, const auto& owner,
                    auto callback, void* user_data, auto** out) {
            return codex_agent_authentication_sign_out(
                context->raw, owner->get(), callback, user_data, out);
        });
}

inline AuthenticationState Authentication::state() const {
    return detail::current_leaf(
        handle_, codex_agent_authentication_state_get,
        detail::read_authentication_state);
}

inline StateSubscription<AuthenticationState> Authentication::subscribe_state(
    std::function<void(StateEvent<AuthenticationState>)> callback) const {
    return detail::subscribe_leaf<
        AuthenticationState, detail::AuthenticationHandle,
        codex_agent_authentication_retain, codex_agent_authentication_release>(
        handle_, codex_agent_authentication_state_subscribe,
        detail::read_authentication_state, std::move(callback));
}

inline bool Authentication::is_authenticated() const {
    return detail::current_leaf(
        handle_, codex_agent_authentication_is_authenticated_get,
        detail::snapshot_boolean);
}

inline StateSubscription<bool> Authentication::subscribe_is_authenticated(
    std::function<void(StateEvent<bool>)> callback) const {
    return detail::subscribe_leaf<
        bool, detail::AuthenticationHandle, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, codex_agent_authentication_is_authenticated_subscribe,
        detail::snapshot_boolean, std::move(callback));
}

inline bool Authentication::is_authenticating() const {
    return detail::current_leaf(
        handle_, codex_agent_authentication_is_authenticating_get,
        detail::snapshot_boolean);
}

inline StateSubscription<bool> Authentication::subscribe_is_authenticating(
    std::function<void(StateEvent<bool>)> callback) const {
    return detail::subscribe_leaf<
        bool, detail::AuthenticationHandle, codex_agent_authentication_retain,
        codex_agent_authentication_release>(
        handle_, codex_agent_authentication_is_authenticating_subscribe,
        detail::snapshot_boolean, std::move(callback));
}

inline AsyncOperation<std::vector<Model>> Models::list() const {
    return detail::leaf_operation<
        std::vector<Model>, codex_agent_models_t, codex_agent_models_retain,
        codex_agent_models_release>(
        handle_, [](const detail::Context& context, const auto& owner,
                    auto callback, void* user_data, auto** out) {
            return codex_agent_models_list(
                context->raw, owner->get(), callback, user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            std::size_t count = 0;
            detail::check(codex_agent_operation_models_count(
                context->raw, operation, &count));
            std::vector<Model> result;
            result.reserve(count);
            for (std::size_t index = 0; index < count; ++index) {
                codex_agent_model_t* raw = nullptr;
                detail::check(codex_agent_operation_model_at(
                    context->raw, operation, index, &raw));
                result.push_back(detail::read_owned<
                    codex_agent_model_t, codex_agent_model_destroy>(
                    context, raw, detail::read_model));
            }
            return result;
        });
}

inline AsyncOperation<Model> Models::resolve(Resolution resolution) const {
    return detail::leaf_operation<
        Model, codex_agent_models_t, codex_agent_models_retain,
        codex_agent_models_release>(
        handle_, [resolution](const detail::Context& context, const auto& owner,
                              auto callback, void* user_data, auto** out) {
            return codex_agent_models_resolve(
                context->raw, owner->get(),
                static_cast<codex_agent_resolution_t>(resolution), callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_model_t* raw = nullptr;
            detail::check(codex_agent_operation_model(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_model_t, codex_agent_model_destroy>(
                context, raw, detail::read_model);
        });
}

inline AsyncOperation<std::string> Models::resolve_effort(
    Model model, Resolution resolution) const {
    auto input = std::make_shared<detail::ModelHandle>(
        detail::make_model(handle_.context(), model));
    return detail::leaf_operation<
        std::string, codex_agent_models_t, codex_agent_models_retain,
        codex_agent_models_release>(
        handle_, [input, resolution](const detail::Context& context,
                                    const auto& owner, auto callback,
                                    void* user_data, auto** out) {
            return codex_agent_models_resolve_effort(
                context->raw, owner->get(), input->get(),
                static_cast<codex_agent_resolution_t>(resolution), callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            return detail::copy_string([&](std::uint8_t* buffer,
                                           std::size_t capacity,
                                           std::size_t* required) {
                return codex_agent_operation_string_copy(
                    context->raw, operation, buffer, capacity, required);
            });
        });
}

inline AsyncOperation<std::optional<ServiceTier>> Models::resolve_service_tier(
    Model model, Resolution resolution) const {
    auto input = std::make_shared<detail::ModelHandle>(
        detail::make_model(handle_.context(), model));
    return detail::leaf_operation<
        std::optional<ServiceTier>, codex_agent_models_t,
        codex_agent_models_retain, codex_agent_models_release>(
        handle_, [input, resolution](const detail::Context& context,
                                    const auto& owner, auto callback,
                                    void* user_data, auto** out) {
            return codex_agent_models_resolve_service_tier(
                context->raw, owner->get(), input->get(),
                static_cast<codex_agent_resolution_t>(resolution), callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation)
            -> std::optional<ServiceTier> {
            std::int32_t present = 0;
            detail::check(codex_agent_operation_has_service_tier(
                context->raw, operation, &present));
            if (present == 0) return std::nullopt;
            codex_agent_service_tier_t* raw = nullptr;
            detail::check(codex_agent_operation_service_tier(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_service_tier_t, codex_agent_service_tier_destroy>(
                context, raw, detail::read_service_tier);
        });
}

inline bool Skills::is_available() const {
    return detail::leaf_available(handle_, codex_agent_skills_is_available);
}

inline AsyncOperation<SkillCatalog> Skills::list(bool force_reload) const {
    return detail::leaf_operation<
        SkillCatalog, codex_agent_skills_t, codex_agent_skills_retain,
        codex_agent_skills_release>(
        handle_, [force_reload](const detail::Context& context,
                               const auto& owner, auto callback,
                               void* user_data, auto** out) {
            return codex_agent_skills_list(
                context->raw, owner->get(), force_reload ? 1 : 0, callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_skill_catalog_t* raw = nullptr;
            detail::check(codex_agent_operation_skill_catalog(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_skill_catalog_t,
                codex_agent_skill_catalog_destroy>(
                context, raw, detail::read_skill_catalog);
        });
}

inline AsyncOperation<SkillChunk> Skills::read(
    std::string path, std::int64_t offset) const {
    return detail::leaf_operation<
        SkillChunk, codex_agent_skills_t, codex_agent_skills_retain,
        codex_agent_skills_release>(
        handle_, [path = std::move(path), offset](
                     const detail::Context& context, const auto& owner,
                     auto callback, void* user_data, auto** out) {
            const auto value = detail::string_view(path);
            return codex_agent_skills_read(
                context->raw, owner->get(), &value, offset, callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_skill_chunk_t* raw = nullptr;
            detail::check(codex_agent_operation_skill_chunk(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_skill_chunk_t, codex_agent_skill_chunk_destroy>(
                context, raw, detail::read_skill_chunk);
        });
}

inline AsyncOperation<Skill> Skills::install(
    std::string directory, InstallationScope scope) const {
    return detail::leaf_operation<
        Skill, codex_agent_skills_t, codex_agent_skills_retain,
        codex_agent_skills_release>(
        handle_, [directory = std::move(directory), scope](
                     const detail::Context& context, const auto& owner,
                     auto callback, void* user_data, auto** out) {
            const auto value = detail::string_view(directory);
            return codex_agent_skills_install(
                context->raw, owner->get(), &value,
                static_cast<codex_agent_installation_scope_t>(scope), callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_skill_t* raw = nullptr;
            detail::check(codex_agent_operation_skill(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_skill_t, codex_agent_skill_destroy>(
                context, raw, detail::read_skill);
        });
}

inline AsyncOperation<void> Skills::uninstall(Skill skill) const {
    auto input = std::make_shared<detail::SkillHandle>(
        detail::make_skill(handle_.context(), skill));
    return detail::leaf_void_operation<
        codex_agent_skills_t, codex_agent_skills_retain,
        codex_agent_skills_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_skills_uninstall(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline bool Hooks::is_available() const {
    return detail::leaf_available(handle_, codex_agent_hooks_is_available);
}

inline AsyncOperation<HookCatalog> Hooks::list() const {
    return detail::leaf_operation<
        HookCatalog, codex_agent_hooks_t, codex_agent_hooks_retain,
        codex_agent_hooks_release>(
        handle_, [](const detail::Context& context, const auto& owner,
                    auto callback, void* user_data, auto** out) {
            return codex_agent_hooks_list(
                context->raw, owner->get(), callback, user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_hook_catalog_t* raw = nullptr;
            detail::check(codex_agent_operation_hook_catalog(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_hook_catalog_t,
                codex_agent_hook_catalog_destroy>(
                context, raw, detail::read_hook_catalog);
        });
}

inline AsyncOperation<Hook> Hooks::install(
    std::string directory, InstallationScope scope) const {
    return detail::leaf_operation<
        Hook, codex_agent_hooks_t, codex_agent_hooks_retain,
        codex_agent_hooks_release>(
        handle_, [directory = std::move(directory), scope](
                     const detail::Context& context, const auto& owner,
                     auto callback, void* user_data, auto** out) {
            const auto value = detail::string_view(directory);
            return codex_agent_hooks_install(
                context->raw, owner->get(), &value,
                static_cast<codex_agent_installation_scope_t>(scope), callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_hook_t* raw = nullptr;
            detail::check(codex_agent_operation_hook(
                context->raw, operation, &raw));
            return detail::read_owned<codex_agent_hook_t,
                                      codex_agent_hook_destroy>(
                context, raw, detail::read_hook);
        });
}

inline AsyncOperation<void> Hooks::uninstall(Hook hook) const {
    auto input = std::make_shared<detail::HookHandle>(
        detail::make_hook(handle_.context(), hook));
    return detail::leaf_void_operation<
        codex_agent_hooks_t, codex_agent_hooks_retain,
        codex_agent_hooks_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_hooks_uninstall(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline AsyncOperation<void> Hooks::trust(Hook hook) const {
    auto input = std::make_shared<detail::HookHandle>(
        detail::make_hook(handle_.context(), hook));
    return detail::leaf_void_operation<
        codex_agent_hooks_t, codex_agent_hooks_retain,
        codex_agent_hooks_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_hooks_trust(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline bool Plugins::is_available() const {
    return detail::leaf_available(handle_, codex_agent_plugins_is_available);
}

inline AsyncOperation<PluginCatalog> Plugins::list(bool force_reload) const {
    return detail::leaf_operation<
        PluginCatalog, codex_agent_plugins_t, codex_agent_plugins_retain,
        codex_agent_plugins_release>(
        handle_, [force_reload](const detail::Context& context,
                               const auto& owner, auto callback,
                               void* user_data, auto** out) {
            return codex_agent_plugins_list(
                context->raw, owner->get(), force_reload ? 1 : 0, callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_plugin_catalog_t* raw = nullptr;
            detail::check(codex_agent_operation_plugin_catalog(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_plugin_catalog_t,
                codex_agent_plugin_catalog_destroy>(
                context, raw, detail::read_plugin_catalog);
        });
}

inline AsyncOperation<PluginDetail> Plugins::read(
    PluginReference plugin) const {
    auto input = std::make_shared<detail::PluginReferenceHandle>(
        detail::make_plugin_reference(handle_.context(), plugin));
    return detail::leaf_operation<
        PluginDetail, codex_agent_plugins_t, codex_agent_plugins_retain,
        codex_agent_plugins_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_plugins_read(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_plugin_detail_t* raw = nullptr;
            detail::check(codex_agent_operation_plugin_detail(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_plugin_detail_t,
                codex_agent_plugin_detail_destroy>(
                context, raw, detail::read_plugin_detail);
        });
}

inline AsyncOperation<PluginInstallResult> Plugins::install(
    PluginReference plugin) const {
    auto input = std::make_shared<detail::PluginReferenceHandle>(
        detail::make_plugin_reference(handle_.context(), plugin));
    return detail::leaf_operation<
        PluginInstallResult, codex_agent_plugins_t, codex_agent_plugins_retain,
        codex_agent_plugins_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_plugins_install(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_plugin_install_result_t* raw = nullptr;
            detail::check(codex_agent_operation_plugin_install_result(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_plugin_install_result_t,
                codex_agent_plugin_install_result_destroy>(
                context, raw, detail::read_plugin_install_result);
        });
}

inline AsyncOperation<void> Plugins::uninstall(PluginReference plugin) const {
    auto input = std::make_shared<detail::PluginReferenceHandle>(
        detail::make_plugin_reference(handle_.context(), plugin));
    return detail::leaf_void_operation<
        codex_agent_plugins_t, codex_agent_plugins_retain,
        codex_agent_plugins_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_plugins_uninstall(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline bool Connectors::is_available() const {
    return detail::leaf_available(handle_, codex_agent_connectors_is_available);
}

inline AsyncOperation<std::vector<Connector>> Connectors::list(
    bool force_reload) const {
    return detail::leaf_operation<
        std::vector<Connector>, codex_agent_connectors_t,
        codex_agent_connectors_retain, codex_agent_connectors_release>(
        handle_, [force_reload](const detail::Context& context,
                               const auto& owner, auto callback,
                               void* user_data, auto** out) {
            return codex_agent_connectors_list(
                context->raw, owner->get(), force_reload ? 1 : 0, callback,
                user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            std::size_t count = 0;
            detail::check(codex_agent_operation_connectors_count(
                context->raw, operation, &count));
            std::vector<Connector> result;
            result.reserve(count);
            for (std::size_t index = 0; index < count; ++index) {
                codex_agent_connector_t* raw = nullptr;
                detail::check(codex_agent_operation_connector_at(
                    context->raw, operation, index, &raw));
                result.push_back(detail::read_owned<
                    codex_agent_connector_t, codex_agent_connector_destroy>(
                    context, raw, detail::read_connector));
            }
            return result;
        });
}

inline bool McpServers::is_available() const {
    return detail::leaf_available(handle_, codex_agent_mcp_servers_is_available);
}

inline AsyncOperation<std::vector<McpServer>> McpServers::list() const {
    return detail::leaf_operation<
        std::vector<McpServer>, codex_agent_mcp_servers_t,
        codex_agent_mcp_servers_retain, codex_agent_mcp_servers_release>(
        handle_, [](const detail::Context& context, const auto& owner,
                    auto callback, void* user_data, auto** out) {
            return codex_agent_mcp_servers_list(
                context->raw, owner->get(), callback, user_data, out);
        },
        [](const detail::Context& context, auto* operation) {
            std::size_t count = 0;
            detail::check(codex_agent_operation_mcp_servers_count(
                context->raw, operation, &count));
            std::vector<McpServer> result;
            result.reserve(count);
            for (std::size_t index = 0; index < count; ++index) {
                codex_agent_mcp_server_t* raw = nullptr;
                detail::check(codex_agent_operation_mcp_server_at(
                    context->raw, operation, index, &raw));
                result.push_back(detail::read_owned<
                    codex_agent_mcp_server_t,
                    codex_agent_mcp_server_destroy>(
                    context, raw, detail::read_mcp_server));
            }
            return result;
        });
}

inline AsyncOperation<McpServer> McpServers::add(
    McpServerConfiguration configuration) const {
    auto input = std::make_shared<detail::McpServerConfigurationHandle>(
        detail::make_mcp_configuration(handle_.context(), configuration));
    return detail::leaf_operation<
        McpServer, codex_agent_mcp_servers_t, codex_agent_mcp_servers_retain,
        codex_agent_mcp_servers_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_mcp_servers_add(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        },
        [](const detail::Context& context, auto* operation) {
            codex_agent_mcp_server_t* raw = nullptr;
            detail::check(codex_agent_operation_mcp_server(
                context->raw, operation, &raw));
            return detail::read_owned<
                codex_agent_mcp_server_t, codex_agent_mcp_server_destroy>(
                context, raw, detail::read_mcp_server);
        });
}

inline AsyncOperation<void> McpServers::remove(McpServer server) const {
    auto input = std::make_shared<detail::McpServerHandle>(
        detail::make_mcp_server(handle_.context(), server));
    return detail::leaf_void_operation<
        codex_agent_mcp_servers_t, codex_agent_mcp_servers_retain,
        codex_agent_mcp_servers_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_mcp_servers_remove(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline AsyncOperation<void> IntegrationAuthorization::authorize(
    IntegrationValue target) const {
    auto input = std::make_shared<detail::IntegrationHandle>(
        detail::make_integration(handle_.context(), target));
    return detail::leaf_void_operation<
        codex_agent_integration_authorization_t,
        codex_agent_integration_authorization_retain,
        codex_agent_integration_authorization_release>(
        handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_integration_authorization_authorize(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline AsyncOperation<void> IntegrationAuthorization::cancel() const {
    return detail::leaf_void_operation<
        codex_agent_integration_authorization_t,
        codex_agent_integration_authorization_retain,
        codex_agent_integration_authorization_release>(
        handle_, [](const detail::Context& context, const auto& owner,
                    auto callback, void* user_data, auto** out) {
            return codex_agent_integration_authorization_cancel(
                context->raw, owner->get(), callback, user_data, out);
        });
}

inline IntegrationAuthorizationState IntegrationAuthorization::state() const {
    return detail::current_leaf(
        handle_, codex_agent_integration_authorization_state_get,
        detail::read_integration_authorization_state);
}

inline StateSubscription<IntegrationAuthorizationState>
IntegrationAuthorization::subscribe_state(
    std::function<void(StateEvent<IntegrationAuthorizationState>)> callback)
    const {
    return detail::subscribe_leaf<
        IntegrationAuthorizationState,
        detail::IntegrationAuthorizationHandle,
        codex_agent_integration_authorization_retain,
        codex_agent_integration_authorization_release>(
        handle_, codex_agent_integration_authorization_state_subscribe,
        detail::read_integration_authorization_state, std::move(callback));
}

inline std::optional<IntegrationValue> IntegrationAuthorization::active() const {
    return detail::current_leaf(
        handle_, codex_agent_integration_authorization_active_get,
        detail::read_active_integration);
}

inline StateSubscription<std::optional<IntegrationValue>>
IntegrationAuthorization::subscribe_active(
    std::function<void(StateEvent<std::optional<IntegrationValue>>)> callback)
    const {
    return detail::subscribe_leaf<
        std::optional<IntegrationValue>,
        detail::IntegrationAuthorizationHandle,
        codex_agent_integration_authorization_retain,
        codex_agent_integration_authorization_release>(
        handle_, codex_agent_integration_authorization_active_subscribe,
        detail::read_active_integration, std::move(callback));
}

inline bool IntegrationAuthorization::is_authorizing() const {
    return detail::current_leaf(
        handle_, codex_agent_integration_authorization_is_authorizing_get,
        detail::snapshot_boolean);
}

inline StateSubscription<bool>
IntegrationAuthorization::subscribe_is_authorizing(
    std::function<void(StateEvent<bool>)> callback) const {
    return detail::subscribe_leaf<
        bool, detail::IntegrationAuthorizationHandle,
        codex_agent_integration_authorization_retain,
        codex_agent_integration_authorization_release>(
        handle_, codex_agent_integration_authorization_is_authorizing_subscribe,
        detail::snapshot_boolean, std::move(callback));
}

inline AsyncOperation<void> Interactions::open_url(
    PendingElicitation elicitation) const {
    if (!elicitation._native_identity ||
        !std::holds_alternative<std::shared_ptr<detail::PendingElicitationHandle>>(
            elicitation._native_identity->value) ||
        elicitation._native_identity->owner != handle_) {
        throw std::invalid_argument(
            "pending elicitation did not originate from this native projection");
    }
    auto input = std::get<std::shared_ptr<detail::PendingElicitationHandle>>(
        elicitation._native_identity->value);
    return detail::leaf_void_operation<
        codex_agent_interactions_t, codex_agent_interactions_retain,
        codex_agent_interactions_release>(
        *handle_, [input](const detail::Context& context, const auto& owner,
                         auto callback, void* user_data, auto** out) {
            return codex_agent_interactions_open_url(
                context->raw, owner->get(), input->get(), callback, user_data,
                out);
        });
}

inline AsyncOperation<void> Interactions::resolve(
    PendingApproval approval, ApprovalDecision decision) const {
    if (!approval._native_identity ||
        !std::holds_alternative<std::shared_ptr<detail::PendingApprovalHandle>>(
            approval._native_identity->value) ||
        approval._native_identity->owner != handle_) {
        throw std::invalid_argument(
            "pending approval did not originate from this native projection");
    }
    auto input = std::get<std::shared_ptr<detail::PendingApprovalHandle>>(
        approval._native_identity->value);
    return detail::leaf_void_operation<
        codex_agent_interactions_t, codex_agent_interactions_retain,
        codex_agent_interactions_release>(
        *handle_, [input, decision](const detail::Context& context,
                                  const auto& owner, auto callback,
                                  void* user_data, auto** out) {
            return codex_agent_interactions_resolve_approval(
                context->raw, owner->get(), input->get(),
                static_cast<codex_agent_approval_decision_t>(decision),
                callback, user_data, out);
        });
}

inline AsyncOperation<void> Interactions::resolve(
    PendingElicitation elicitation, ElicitationResponse response) const {
    if (!elicitation._native_identity ||
        !std::holds_alternative<std::shared_ptr<detail::PendingElicitationHandle>>(
            elicitation._native_identity->value) ||
        elicitation._native_identity->owner != handle_) {
        throw std::invalid_argument(
            "pending elicitation did not originate from this native projection");
    }
    auto input = std::get<std::shared_ptr<detail::PendingElicitationHandle>>(
        elicitation._native_identity->value);
    auto native_response =
        std::make_shared<detail::ElicitationResponseHandle>(
            detail::make_elicitation_response(handle_->context(), response));
    return detail::leaf_void_operation<
        codex_agent_interactions_t, codex_agent_interactions_retain,
        codex_agent_interactions_release>(
        *handle_, [input, native_response](
                     const detail::Context& context, const auto& owner,
                     auto callback, void* user_data, auto** out) {
            return codex_agent_interactions_resolve_elicitation(
                context->raw, owner->get(), input->get(),
                native_response->get(), callback, user_data, out);
        });
}

inline InteractionState Interactions::state() const {
    return detail::current_leaf(
        *handle_, codex_agent_interactions_state_get,
        [owner = handle_](const detail::Context& context,
                          codex_agent_snapshot_t* snapshot) {
            return detail::read_interaction_state(context, snapshot, owner);
        });
}

inline StateSubscription<InteractionState> Interactions::subscribe_state(
    std::function<void(StateEvent<InteractionState>)> callback) const {
    return detail::subscribe_leaf<
        InteractionState, detail::InteractionsHandle,
        codex_agent_interactions_retain, codex_agent_interactions_release>(
        *handle_, codex_agent_interactions_state_subscribe,
        [owner = handle_](const detail::Context& context,
                          codex_agent_snapshot_t* snapshot) {
            return detail::read_interaction_state(context, snapshot, owner);
        },
        std::move(callback));
}

inline std::vector<PendingApproval> Interactions::approvals() const {
    return detail::current_leaf(
        *handle_, codex_agent_interactions_approvals_get,
        [owner = handle_](const detail::Context& context,
                          codex_agent_snapshot_t* snapshot) {
            return detail::read_approvals(context, snapshot, owner);
        });
}

inline StateSubscription<std::vector<PendingApproval>>
Interactions::subscribe_approvals(
    std::function<void(StateEvent<std::vector<PendingApproval>>)> callback)
    const {
    return detail::subscribe_leaf<
        std::vector<PendingApproval>, detail::InteractionsHandle,
        codex_agent_interactions_retain, codex_agent_interactions_release>(
        *handle_, codex_agent_interactions_approvals_subscribe,
        [owner = handle_](const detail::Context& context,
                          codex_agent_snapshot_t* snapshot) {
            return detail::read_approvals(context, snapshot, owner);
        },
        std::move(callback));
}

inline std::vector<PendingElicitation> Interactions::elicitations() const {
    return detail::current_leaf(
        *handle_, codex_agent_interactions_elicitations_get,
        [owner = handle_](const detail::Context& context,
                          codex_agent_snapshot_t* snapshot) {
            return detail::read_elicitations(context, snapshot, owner);
        });
}

inline StateSubscription<std::vector<PendingElicitation>>
Interactions::subscribe_elicitations(
    std::function<void(StateEvent<std::vector<PendingElicitation>>)> callback)
    const {
    return detail::subscribe_leaf<
        std::vector<PendingElicitation>, detail::InteractionsHandle,
        codex_agent_interactions_retain, codex_agent_interactions_release>(
        *handle_, codex_agent_interactions_elicitations_subscribe,
        [owner = handle_](const detail::Context& context,
                          codex_agent_snapshot_t* snapshot) {
            return detail::read_elicitations(context, snapshot, owner);
        },
        std::move(callback));
}

}  // namespace codex_agent
