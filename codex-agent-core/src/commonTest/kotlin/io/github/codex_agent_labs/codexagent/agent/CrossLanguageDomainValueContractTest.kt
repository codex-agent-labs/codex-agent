package io.github.codex_agent_labs.codexagent.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class CrossLanguageDomainValueContractTest {
    @Test
    @CoversApi(
        "api-v1:AgentHookHandler.Agent#object:Agent#sha256:61e3a7cef5071600137f48bdf8dca742486c94a657929be2f92fa40032f7f303",
        "api-v1:AgentHookHandler.Prompt#object:Prompt#sha256:9686f30dd500d87a7f8023d04d31f259705e3ccefef29be994b9d4a81177abd5",
        "api-v1:CodexAuthenticationMethod.ChatGptBrowser#object:ChatGptBrowser#sha256:31fdd97dd88d98f8f6f1077d654a72de750d0cb322f79874137585b2a9db8518",
        "api-v1:CodexAuthenticationMethod.ChatGptDeviceCode#object:ChatGptDeviceCode#sha256:c13a3661dd90d28e5f967585323fd2cc117aec5f7b12dae763f2a52e30faca1b",
        "api-v1:CodexHostState.Closed#object:Closed#sha256:2a00547a7621cd95c3ef6db4a508e57dca1bc567997b376bcadcea0598a21da9",
        "api-v1:CodexHostState.New#object:New#sha256:5232201a978a92d8e6c6f7e6dd7e85b938f16e0134b933cef47c0f773dd56d53",
        "api-v1:CodexHostState.Restoring#object:Restoring#sha256:6537c0aedbf6bc8ff351e72f44518cf489696959389dfc708be981b6646ebd05",
    )
    fun singletonVariantsExposeStableDistinctValues() {
        val handlers: List<AgentHookHandler> = listOf(AgentHookHandler.Agent, AgentHookHandler.Prompt)
        val authenticationMethods: List<CodexAuthenticationMethod> = listOf(
            CodexAuthenticationMethod.ChatGptBrowser,
            CodexAuthenticationMethod.ChatGptDeviceCode,
        )
        val hostStates: List<CodexHostState> = listOf(
            CodexHostState.New,
            CodexHostState.Restoring,
            CodexHostState.Closed,
        )

        assertEquals(handlers.size, handlers.toSet().size)
        assertEquals(authenticationMethods.size, authenticationMethods.toSet().size)
        assertEquals(hostStates.size, hostStates.toSet().size)
        assertTrue(handlers.first() === AgentHookHandler.Agent)
        assertTrue(authenticationMethods.first() === CodexAuthenticationMethod.ChatGptBrowser)
        assertTrue(hostStates.first() === CodexHostState.New)
    }

    @Test
    @CoversApi(
        "api-v1:AgentApprovalDecision#enum-entry:DECLINE#sha256:c152818b78520d8d40a7902ec1e524edbde2556d96370e01c4285fa0076bd756",
        "api-v1:AgentApprovalPreset#enum-entry:ASK_ME#sha256:1c91d695f0bf7b4ae9fed9685f478116c2a9b187145e168a7ed4d20d706e9eff",
        "api-v1:AgentApprovalPreset#enum-entry:AUTO_REVIEW#sha256:ffe709a67a9f7b98c30a169ba331630030ba947df889389fd084f27a1170ee68",
        "api-v1:AgentApprovalPreset#enum-entry:NEVER#sha256:f78008578198387bf29235e7b9d3eb7269feb1883af800713b5db11cab14c0d4",
        "api-v1:AgentApprovalPreset#enum-entry:STRICT#sha256:7c0ad5d0af642547e82058257c37dc8bda26edb2749ec2f9663132a3cbc1dce8",
        "api-v1:AgentApprovalPreset#property:displayName#sha256:16f55e295f11732025e0209352cd28a75dfaf293aa544afaf1c613d107841465",
        "api-v1:AgentCapability#property:icon#sha256:dff8d6aa0e453c5921f6b5df68e8a1f055fe6a3c772439038c49c762904602fc",
        "api-v1:AgentCapability#property:id#sha256:76021639370f61ea9897dd3b3d207fdf1718c4705dbff3345799803fd135fbee",
        "api-v1:AgentCollaborationMode#enum-entry:DEFAULT#sha256:6d5290f01f4836d5bf0c09e94f50ec3d1fc8cae7ab0b3dd6225a7e4ea5d5008e",
        "api-v1:AgentConversationSettings#constructor:<init>#sha256:15b1648cdc3773b382241bc7d7f83029c8e671d615ac367ab6340218bf0d5318",
        "api-v1:AgentConversationSettings#property:approvalPreset#sha256:e379ad866394a7c8cb1c4755674f89bae5ef32855e19559a6116914509de38f3",
        "api-v1:AgentConversationSettings#property:serviceTier#sha256:6a410376bd30dd0f7603c8cdc37aec0f25a27b30ede2665bbd4fc6d0570cda34",
        "api-v1:AgentConversationSummary#constructor:<init>#sha256:f52290f2720700a9631fcaad0ec0c0502fe3b9b16ec065cd231e8bcf2024d1d3",
        "api-v1:AgentConversationSummary#property:conversationId#sha256:196b6d7ed9e3f7df39ce1b12e421e536101fc3f0de5017acc27719c95e86cc61",
        "api-v1:AgentConversationSummary#property:updatedAtEpochSeconds#sha256:b1deca99163db18a93f7e426e0e3db3b7139202f15ac5bcec268c9a95f45d360",
        "api-v1:AgentHook#property:currentHash#sha256:d0df88aaaae8c82ec9561d93ad135bc24d7614f1fd43f2a55c90e45a73dc3920",
        "api-v1:AgentHook#property:eventName#sha256:a1c5e468abc4c438efa290aac1e3c92df23a0fcad99ab54da3a479e412e11a2e",
        "api-v1:AgentHook#property:handler#sha256:440c99d220effdde15ce80c11fa60743036a14f5638b1725f71f0869111b5609",
        "api-v1:AgentHook#property:isEnabled#sha256:281c261d07d8ef76ff6920abcfcb73606cdd95d15247781cc4e192f6b75338da",
        "api-v1:AgentHook#property:isManaged#sha256:47d9593d59da39ad0300c9fa4d19525a083d34776de738cc16e6381805176ba2",
        "api-v1:AgentHook#property:matcher#sha256:d07a84d6542d1d4d39ecf848eab5f6e86d8d626b69e8201cd1ecf7d81410e27b",
        "api-v1:AgentHook#property:pluginId#sha256:8b11012f8fa3ae99bfad1d10dab3aca75e487fc277a12d01e90e965cbaad9bfa",
        "api-v1:AgentHook#property:source#sha256:ce40948daef8541b247c4c181fa742c1ae3db832a41c6e71bec98a0729ad74dd",
        "api-v1:AgentHook#property:statusMessage#sha256:fb3ebf1e2910a63a75428110ba4353dd7d61293f57fe3ebe12ec35ae8c12dc32",
        "api-v1:AgentHook#property:timeoutSeconds#sha256:5a7cc82938e7e0187821416f80ebaeaa5f0a90e8d6825941914fb52a424d5059",
        "api-v1:AgentHook#property:trustStatus#sha256:9ab32a1396dd86af1bb5577503cefcd59e012cf4569f861801ea24e51b3c9719",
        "api-v1:AgentHookActivity#property:details#sha256:b8849ff7a6af21c8b856216dad418739f336769845e02be95be9a61eb22d5a5b",
        "api-v1:AgentHookActivity#property:eventName#sha256:9d88b122ebb2e4f8c2e8c872ddd5f2fea038ded7cf8a65906e925fcd8243474f",
        "api-v1:AgentHookActivity#property:handlerType#sha256:9c28fa98631ac7eecd34589da8abe0bcce2929d157990fd3cf409b3e32d017d9",
        "api-v1:AgentHookActivity#property:statusMessage#sha256:da385772ffe8b72ac6eca3b784910a581958bcf5c52d90a0988d987c4612b9e7",
        "api-v1:AgentHookActivity#property:status#sha256:1bf433450a12d54881dc95860f42b0f58d0f7cd8bdd016865d2c192f858bd798",
        "api-v1:AgentHookCatalog#property:errors#sha256:5c8013610462e52cd8ab011f39df8846bfb740a80a9dd4b3e0770e0bb33d034c",
        "api-v1:AgentHookCatalog#property:warnings#sha256:aa8b3497d773ce9ab6d0472f3da4e7e88e7130f60557dd30e9592ff996396cc1",
        "api-v1:AgentHookHandler.Command#constructor:<init>#sha256:1a41efda6d35e6118e7bbeeca6229d7c7858f313e458cf70d1e36a0508d057cf",
        "api-v1:AgentHookHandler.Command#property:command#sha256:88d252a3636685065c6267d7ded310fce43f22e5e67a2193c7c6e10ee9740792",
        "api-v1:AgentHookHandler.Command#property:isAsync#sha256:8461e21fcb2a551a554ef55c523a16ea80df750a76e9380d832c0b80c47fa947",
        "api-v1:AgentHookHandler.McpTool#constructor:<init>#sha256:8a62b8483719c4160f0ae5baae646a2a5482070d9abd2614699f98583798de81",
        "api-v1:AgentHookHandler.McpTool#property:server#sha256:ceb442ae9dccfbadec81b244b29c84787e89500b2ce321e1635c2384c44f5bf2",
        "api-v1:AgentHookHandler.McpTool#property:tool#sha256:b1da937595f42cc75a066684ba027047907f91b59b7c0c32723d5f8064d4253b",
        "api-v1:AgentHookRunStatus#enum-entry:BLOCKED#sha256:fe06c01541a86c4dfa1eacef4431668f408f3eaea186c15093d7f4ded88efa76",
        "api-v1:AgentHookRunStatus#enum-entry:COMPLETED#sha256:9302758dbabed232607818afbd8e75d1b862d978550577ba21d2b9a4b47e6cd0",
        "api-v1:AgentHookRunStatus#enum-entry:FAILED#sha256:15ad0bcc5ab72d63cf9b08abbeb3f712b27cd7c67907f3aa6c1f604d022c7d3c",
        "api-v1:AgentHookRunStatus#enum-entry:STOPPED#sha256:87105f0bb3d249545dd134eba44567a5792aa17e98ef14f9fdae5ca15f419889",
        "api-v1:AgentMessage#property:collaborationMode#sha256:0c448381eee0a67a91fea033b077510fb88b25fa3fdf779aa6b98e767ecd863f",
        "api-v1:AgentMessage#property:invocations#sha256:978c78053aa8206477d8427c0f5ca7c927918bb5a2a29f371d92772891555a94",
        "api-v1:AgentMessage#property:plan#sha256:cc1048d9f3db2a8e098955aa6d5a8420160b4b9879a7cac65f20b62d322523f5",
        "api-v1:AgentModel#property:description#sha256:bdcd000a32d55208aed3b4d2babd63f3d5e180d07907d51b69e550eed37eda4b",
        "api-v1:AgentModel#property:displayName#sha256:ff9deb3e2827d63d133b470702e9f895b3ede2e6ad6b22b33e6f2299f65164d3",
        "api-v1:AgentPlanProgress#property:explanation#sha256:3e61a5e618a3b6a05e92e233da08f49d27be4ab302898e3ca7e1ea13ee9eb43e",
        "api-v1:AgentPlanStep#property:status#sha256:05f4b4a17e219263feabab30f6c437bb0f4e01ff9ab2fc5bfafca0422d72a6aa",
        "api-v1:AgentPlanStepStatus#enum-entry:COMPLETED#sha256:3529f95fc04d0fd6cac3f4ed3bfccb49db64bc2b8c75e73c8f8f7f4eb8722506",
        "api-v1:AgentPlanStepStatus#enum-entry:PENDING#sha256:37b61a15dcbb1185bbd86c88306f1f072f6c9eddf66aa222705f99b21daa56dc",
        "api-v1:AgentServiceTier#property:description#sha256:faabba00a286ee05ab93caa8e570106bc43c0d78e3f85fa62faf58c4ddd5c91e",
        "api-v1:AgentServiceTier#property:name#sha256:a96e16d7d316b75a15e72edd503c176dd585a1b6393720e85d4ae5b42aa1930a",
        "api-v1:AgentTurnRequest#property:approvalPreset#sha256:cf0e0714e329c48d508d86677e324cb7eaea2ba4f2d414a175a565e37e9780d3",
        "api-v1:AgentTurnRequest#property:serviceTier#sha256:c76f1b4fa2bba443fabd67d96413c0f1d9d8bd2fe5cdf2bc79e1cc6fb49e32af",
        "api-v1:AgentWorkActivity#enum-entry:RUNNING_COMMAND#sha256:df820128ed5c7dfa6ff0a3ab434c76af9f460f089d9716fe6eff6c880870c44e",
    )
    fun conversationValuesExposeEverySupportedFieldAndVariant() {
        assertEquals(
            listOf(
                AgentApprovalPreset.NEVER,
                AgentApprovalPreset.AUTO_REVIEW,
                AgentApprovalPreset.ASK_ME,
                AgentApprovalPreset.STRICT,
            ),
            AgentApprovalPreset.entries.toList(),
        )
        assertEquals(listOf("Never", "Auto review", "Ask me", "Strict"), AgentApprovalPreset.entries.map { it.displayName })
        assertEquals(
            listOf(AgentApprovalDecision.ACCEPT, AgentApprovalDecision.DECLINE),
            AgentApprovalDecision.entries.toList(),
        )

        val capability = AgentCapability.WEB_SEARCH
        assertEquals(listOf("web_search", "🌐"), listOf(capability.id, capability.icon))
        val tier = AgentServiceTier("fast", "Fast", "Low-latency service")
        val model = AgentModel(
            id = "codex",
            displayName = "Codex",
            description = "Coding model",
            supportedEfforts = listOf("low", "high"),
            defaultEffort = "high",
            isDefault = true,
            serviceTiers = listOf(tier),
            defaultServiceTier = tier.id,
        )
        assertEquals(listOf("Fast", "Low-latency service"), listOf(tier.name, tier.description))
        assertEquals(
            listOf("Codex", "Coding model", listOf(tier), "fast"),
            listOf(model.displayName, model.description, model.serviceTiers, model.defaultServiceTier),
        )

        val settings = AgentConversationSettings(AgentApprovalPreset.STRICT, "fast")
        assertEquals(listOf(AgentApprovalPreset.STRICT, "fast"), listOf(settings.approvalPreset, settings.serviceTier))
        val conversationId = ConversationId("conversation-1")
        val summary = AgentConversationSummary(conversationId, "Title", 42)
        assertEquals(listOf(conversationId, 42L), listOf(summary.conversationId, summary.updatedAtEpochSeconds))
        val invocation = AgentInvocation.Skill("review", "/skills/review/SKILL.md")
        val message = AgentMessage(
            "message-1",
            null,
            AgentMessageRole.ASSISTANT,
            "Done",
            collaborationMode = AgentCollaborationMode.DEFAULT,
            plan = "Ship",
            invocations = listOf(invocation),
        )
        assertEquals(
            listOf(AgentCollaborationMode.DEFAULT, listOf(invocation), "Ship"),
            listOf(message.collaborationMode, message.invocations, message.plan),
        )

        val steps = listOf(
            AgentPlanStep("inspect", AgentPlanStepStatus.PENDING),
            AgentPlanStep("ship", AgentPlanStepStatus.COMPLETED),
        )
        val plan = AgentPlanProgress("Ready", steps)
        assertEquals("Ready", plan.explanation)
        assertEquals(
            listOf(AgentPlanStepStatus.PENDING, AgentPlanStepStatus.COMPLETED),
            steps.map(AgentPlanStep::status),
        )
        assertEquals(
            listOf(AgentPlanStepStatus.PENDING, AgentPlanStepStatus.IN_PROGRESS, AgentPlanStepStatus.COMPLETED),
            AgentPlanStepStatus.entries.toList(),
        )
        assertEquals(
            listOf(
                AgentHookRunStatus.RUNNING,
                AgentHookRunStatus.COMPLETED,
                AgentHookRunStatus.FAILED,
                AgentHookRunStatus.BLOCKED,
                AgentHookRunStatus.STOPPED,
            ),
            AgentHookRunStatus.entries.toList(),
        )
        assertEquals(
            listOf(AgentWorkActivity.RUNNING_COMMAND, AgentWorkActivity.WRITING_FILES),
            AgentWorkActivity.entries.toList(),
        )

        val activity = AgentHookActivity(
            id = "hook-1",
            eventName = "afterTurn",
            handlerType = "command",
            status = AgentHookRunStatus.COMPLETED,
            statusMessage = "Complete",
            details = listOf("ok"),
        )
        assertEquals(
            listOf("afterTurn", "command", AgentHookRunStatus.COMPLETED, "Complete", listOf("ok")),
            listOf(activity.eventName, activity.handlerType, activity.status, activity.statusMessage, activity.details),
        )
        val commandHandler = AgentHookHandler.Command("echo ready", false)
        val hook = AgentHook(
            key = "hook",
            currentHash = "hash",
            isEnabled = true,
            eventName = "afterTurn",
            handler = commandHandler,
            isManaged = false,
            source = "PLUGIN",
            sourcePath = "/hooks.json",
            timeoutSeconds = 10,
            trustStatus = AgentHookTrustStatus.MODIFIED,
            matcher = "*.kt",
            pluginId = "review-plugin",
            statusMessage = "Review",
        )
        assertEquals(listOf("echo ready", false), listOf(commandHandler.command, commandHandler.isAsync))
        val mcpHandler = AgentHookHandler.McpTool("server", "review")
        assertEquals(listOf("server", "review"), listOf(mcpHandler.server, mcpHandler.tool))
        assertEquals(
            listOf(
                "hash",
                "afterTurn",
                commandHandler,
                true,
                false,
                "*.kt",
                "review-plugin",
                "PLUGIN",
                "Review",
                10L,
                AgentHookTrustStatus.MODIFIED,
            ),
            listOf(
                hook.currentHash,
                hook.eventName,
                hook.handler,
                hook.isEnabled,
                hook.isManaged,
                hook.matcher,
                hook.pluginId,
                hook.source,
                hook.statusMessage,
                hook.timeoutSeconds,
                hook.trustStatus,
            ),
        )
        val hookCatalog = AgentHookCatalog(listOf(hook), warnings = listOf("warning"), errors = listOf("error"))
        assertEquals(listOf(listOf("warning"), listOf("error")), listOf(hookCatalog.warnings, hookCatalog.errors))

        val state = AgentConversationState(
            status = AgentConversationStatus.READY,
            conversationId = conversationId,
            model = model.id,
            effort = "high",
            serviceTier = tier.id,
        )
        assertEquals(listOf("high", "fast"), listOf(state.effort, state.serviceTier))
        val request = AgentTurnRequest(
            "Review",
            serviceTier = "fast",
            approvalPreset = AgentApprovalPreset.STRICT,
        )
        assertEquals(
            listOf(AgentApprovalPreset.STRICT, "fast"),
            listOf(request.approvalPreset, request.serviceTier),
        )
    }

    @Test
    @CoversApi(
        "api-v1:AgentConnector#constructor:<init>#sha256:bc92fe5ef2c528d08df282e93baf26a1c2860ffaec3b214840d7385e7f03e0f0",
        "api-v1:AgentConnector#property:description#sha256:2d6e09097f57b4dc82e75943496c8b08499473b6ab3f8477f322f1a9215a9d75",
        "api-v1:AgentConnector#property:installUrl#sha256:6208293a82b339cf32efd64e39abd16822e6b952ba69176db8d021f0324a6285",
        "api-v1:AgentConnector#property:isEnabled#sha256:c015b036e2a7ed08a700b09bc640453af16812371b3cc081d6ee38b40d163e2b",
        "api-v1:AgentConnector#property:name#sha256:065be45a17a2efede678a49b956082d8010ee5c96294bc7238fe13ddbcd2902f",
        "api-v1:AgentConnector#property:pluginNames#sha256:d6c1aad265127c9e8264726b2263fb181bea411c84c43fbe75bc3ded53b2ca33",
        "api-v1:AgentMcpEnvironmentSource#enum-entry:LOCAL#sha256:281dcaca62ac0fce585283ae007767e8f05cb35ae7c18ff06ede81b92b34c72b",
        "api-v1:AgentMcpServer#property:authStatus#sha256:ccf1033bf7b7b46df86db4be8bd07b63f7ea3fc0c589f9fa5e522f351f2fec53",
        "api-v1:AgentMcpServer#property:displayName#sha256:90dd59b96c1ff26dbd684f3047b30c1ebb06082ab043b8a383ff5293aec07f54",
        "api-v1:AgentMcpToolApproval#enum-entry:APPROVE#sha256:d9f0424bd36a72f76a45b7999f1f831613f9d187869fcdf5f8d39669c2a495c6",
        "api-v1:AgentMcpToolApproval#enum-entry:AUTO#sha256:82785c95d863571feadd1ddb6dbc0ee7c1a9e02fa50334a8c7eeb27bbd808146",
        "api-v1:AgentMcpToolExposureSurface#enum-entry:DIRECT#sha256:0525dad330a1140574ef79386c10e8c43b515b2298243b5d4687b7005f89a90f",
        "api-v1:AgentPluginDetail#constructor:<init>#sha256:b064994e912f54d6de05c7a91354404b1a6084bd8b252dea12c683a70195983d",
        "api-v1:AgentPluginDetail#property:description#sha256:f65aa0d1855af9ec69213f66b26677b6c3ca754d3e8db9e4bc5e23b1d6bdb49a",
        "api-v1:AgentPluginDetail#property:hookCount#sha256:6e36542531b80cdc9b56e2d8f1f96bf7e69642ecd3a3dd30bb273209ede31da0",
        "api-v1:AgentPluginDetail#property:mcpServers#sha256:9fe3848f3819892139afc0d9b6a23d1cd4badeecc5187c27926248f0c49c5f0f",
        "api-v1:AgentPluginDetail#property:skills#sha256:aaebd27df7f5eeebdf47d593a02baadd153ddd678c519d353d4dde0ec14422a8",
        "api-v1:AgentPluginDetail#property:summary#sha256:fd217568b8c0df303d465c3a9873ff5e491385b48d62aeb5ccdd021aba18634a",
        "api-v1:AgentPluginInstallPolicy#enum-entry:NOT_AVAILABLE#sha256:515d3dddf52ec44d1d6515fb9a5a066695b498dd79309990cb4dfbc1096900f0",
        "api-v1:AgentPluginInstallResult#constructor:<init>#sha256:f3100600123c591f6c7e69ece75177060d0b491d60fd3a43dccd101c6d2cc2a8",
        "api-v1:AgentPluginInstallResult#property:authPolicy#sha256:685d664a284d420b7dc39a9d7216956aa99bdc0a9bc0ce905b385b280f410d49",
        "api-v1:AgentPluginInstallResult#property:message#sha256:83c5b70e8ede6b5b469a96149dcbce847a17d8e623e5207843946891ec574434",
        "api-v1:AgentPluginReference#property:marketplaceName#sha256:60516209ce318807533aa1b51415242afccbdcdfe2406020dc3acb5f33c93dd4",
        "api-v1:AgentPluginReference#property:marketplacePath#sha256:07dbfe889bade767710dece4a18d8094b7c2aaaa6984e164ac93e3cbf2e75afc",
        "api-v1:AgentPluginReference#property:name#sha256:3ded940fbdd13ae4aa997b5d8d834c8a82b8ed4669ce076ec373969ba9e1cf62",
        "api-v1:AgentPluginReference#property:uri#sha256:ce22ea26823b89ac810b8965ea097025893beec847df314ef41da35967f7b5fd",
        "api-v1:AgentPluginSkill#constructor:<init>#sha256:e3e3dd5acd116d18e1d8259f7d0991b9db3ecd9b1817d134d54f329ba39ad9a0",
        "api-v1:AgentPluginSkill#property:description#sha256:521dcc847c7316514dcfca8e718500e233a95595171161f6ea16723cad4056d5",
        "api-v1:AgentPluginSkill#property:isEnabled#sha256:233345beda79e654a6e64f88701f2ca56dffe5e07e0ef65c09c42cbd06ddcdf7",
        "api-v1:AgentPluginSkill#property:name#sha256:4a483962154a51f5835f4024494f39bf1ef405418d7f6e47beabdc138bb238dd",
        "api-v1:AgentPluginSkill#property:path#sha256:f513aa50b293f8b63169d9bbc06ec3be812dd997cbbdd618ef336bebb287a0c3",
        "api-v1:AgentPluginSummary#property:brandColor#sha256:877623ebd3ac00f7c4b916accdb0ca2fceb1af9b11562ea362ec7d02c9936b31",
        "api-v1:AgentPluginSummary#property:capabilities#sha256:54dc581026e706c196b22074d9051a5be9261f4ae44552e540981b56ef2061e8",
        "api-v1:AgentPluginSummary#property:isAvailable#sha256:e2e9c439c1ffdf6feb780c3ac2953585f1978e8f13fa93589bd784de4f43c09f",
        "api-v1:AgentPluginSummary#property:privacyPolicyUrl#sha256:4312f3794675f098724337fbdbbd1150583e7c7b55ac9bff36872da56410b466",
        "api-v1:AgentPluginSummary#property:termsOfServiceUrl#sha256:df395fcc7138de731adaaae4b2aad38caeac1e8571cb473303b4db6b63812cbb",
        "api-v1:AgentPluginSummary#property:websiteUrl#sha256:dafad866513a44523138c6e702665b5db9f6c08a049c7a30243ee8c26d0de2a5",
        "api-v1:AgentResourceOrigin#enum-entry:MANAGED#sha256:7ab4e16b6d6ced2fd83a625f86f9376527847ad6f8392210eb078104f4e88a84",
        "api-v1:AgentResourceOrigin#enum-entry:PLUGIN#sha256:e19352a3d0ade47f6988c7926c3c06a7a4743b3e0563d42446f2e734ba269417",
        "api-v1:AgentResourceOrigin#enum-entry:UNKNOWN#sha256:0d6615800094eacce39ed45a189482e903e724c5e88d87f569424650c27dae41",
        "api-v1:AgentSkill#property:brandColor#sha256:15de52f7ac7a44a17eb998c21e29d9ce59206c9b353a481ba90ee08d33936361",
        "api-v1:AgentSkill#property:dependencies#sha256:0fb69b61bc67d2735281fdda4d6e6a028c8a56ef48e9e893794d7cd9e039bc78",
        "api-v1:AgentSkill#property:description#sha256:37376551103f035ac93aec79a563511be02aab53ad8e5fccdcf5adc95f4b7fd1",
        "api-v1:AgentSkill#property:displayName#sha256:00221d75a3d8a9c6ac357f251dc7da18ed51e3ae9560cc1a76bf2f2ece54cbc2",
        "api-v1:AgentSkill#property:isEnabled#sha256:185a3c9c6f6dbcefb06cbaacacfc8f73521aed1c62ba21c192771e67a6de7ead",
        "api-v1:AgentSkill#property:scope#sha256:d2beabc64aa2bfa9679ab3e8f4d3563af22cf6a24507dd619992d99dcfc9f5c3",
        "api-v1:AgentSkillCatalog#property:errors#sha256:6aa2e1190164854bc54746f9239f095160af7c72d1656da93df4103902354fcb",
        "api-v1:AgentSkillChunk#constructor:<init>#sha256:19c07a8c422817aacecb09fcf31338ff9fbff0d94176ca8b4b4905dd43486cb3",
        "api-v1:AgentSkillChunk#property:totalBytes#sha256:7fda2427eb5ac7f8c65020604042ff27f9e8c32f45a089de9d73aa0911f2ba14",
        "api-v1:AgentSkillScope#enum-entry:ADMIN#sha256:e1605d76c179c9a2940cb4cfcb7c5b7421c51a123a69ae94972b35a8692c15af",
        "api-v1:AgentSkillScope#enum-entry:PLUGIN#sha256:28a75347e31d50ac438334b62b65ab7b53af1c794754ff521a035bd339a72605",
        "api-v1:AgentSkillScope#enum-entry:SYSTEM#sha256:171ba6429bd30d982b9533b14fb39c188a9772171243d7e4095f686ff18dec21",
        "api-v1:AgentSkillScope#property:displayName#sha256:94edf2f6502b58cb63a7471adb5bff33e22524b5ee8d0c6de274cf0e41d69b50",
    )
    fun extensionAndMcpValuesExposeEverySupportedFieldAndVariant() {
        assertEquals(
            listOf(
                AgentSkillScope.SYSTEM,
                AgentSkillScope.USER,
                AgentSkillScope.REPO,
                AgentSkillScope.PLUGIN,
                AgentSkillScope.ADMIN,
            ),
            AgentSkillScope.entries.toList(),
        )
        assertEquals(
            listOf("Built in", "User", "Workspace", "Plugin", "Managed"),
            AgentSkillScope.entries.map { it.displayName },
        )
        assertEquals(
            listOf(
                AgentResourceOrigin.USER,
                AgentResourceOrigin.WORKSPACE,
                AgentResourceOrigin.PLUGIN,
                AgentResourceOrigin.MANAGED,
                AgentResourceOrigin.UNKNOWN,
            ),
            AgentResourceOrigin.entries.toList(),
        )

        val skill = AgentSkill(
            name = "review",
            displayName = "Review",
            description = "Review changes",
            path = "/skills/review/SKILL.md",
            scope = AgentSkillScope.PLUGIN,
            isEnabled = true,
            brandColor = "#123456",
            dependencies = listOf("git"),
            canUninstall = true,
        )
        assertEquals(
            listOf(
                "Review",
                "Review changes",
                AgentSkillScope.PLUGIN,
                true,
                "#123456",
                listOf("git"),
                true,
                AgentResourceOrigin.PLUGIN,
            ),
            listOf(
                skill.displayName,
                skill.description,
                skill.scope,
                skill.isEnabled,
                skill.brandColor,
                skill.dependencies,
                skill.canUninstall,
                skill.origin,
            ),
        )
        assertEquals(listOf("warning"), AgentSkillCatalog(listOf(skill), listOf("warning")).errors)
        assertEquals(20L, AgentSkillChunk("content", 7, 20).totalBytes)

        val reference = AgentPluginReference("drive", "drive", "marketplace", "/marketplace", "remote")
        assertEquals(
            listOf("drive", "marketplace", "/marketplace", "plugin://drive@marketplace"),
            listOf(reference.name, reference.marketplaceName, reference.marketplacePath, reference.uri),
        )
        assertEquals(
            listOf(
                AgentPluginInstallPolicy.NOT_AVAILABLE,
                AgentPluginInstallPolicy.AVAILABLE,
                AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT,
            ),
            AgentPluginInstallPolicy.entries.toList(),
        )
        val summary = AgentPluginSummary(
            reference = reference,
            displayName = "Drive",
            description = "Files",
            isInstalled = true,
            isEnabled = true,
            installPolicy = AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT,
            authPolicy = AgentPluginAuthPolicy.ON_INSTALL,
            isAvailable = true,
            capabilities = listOf("search"),
            brandColor = "#abcdef",
            privacyPolicyUrl = "https://example.com/privacy",
            termsOfServiceUrl = "https://example.com/terms",
            websiteUrl = "https://example.com",
        )
        assertEquals(
            listOf(
                true,
                listOf("search"),
                "#abcdef",
                "https://example.com/privacy",
                "https://example.com/terms",
                "https://example.com",
            ),
            listOf(
                summary.isAvailable,
                summary.capabilities,
                summary.brandColor,
                summary.privacyPolicyUrl,
                summary.termsOfServiceUrl,
                summary.websiteUrl,
            ),
        )
        val pluginSkill = AgentPluginSkill("review", "Review", true, "/skills/review")
        assertEquals(
            listOf("review", "Review", true, "/skills/review"),
            listOf(pluginSkill.name, pluginSkill.description, pluginSkill.isEnabled, pluginSkill.path),
        )
        val connector = AgentConnector(
            "drive",
            "Drive",
            description = "Files",
            installUrl = "https://example.com/install",
            isEnabled = false,
            pluginNames = listOf("plugin"),
        )
        assertEquals(
            listOf("Drive", "Files", "https://example.com/install", false, listOf("plugin")),
            listOf(connector.name, connector.description, connector.installUrl, connector.isEnabled, connector.pluginNames),
        )
        val detail = AgentPluginDetail(summary, "Details", listOf(pluginSkill), listOf(connector), listOf("mcp"), 2)
        assertEquals(
            listOf(summary, "Details", listOf(pluginSkill), listOf("mcp"), 2),
            listOf(detail.summary, detail.description, detail.skills, detail.mcpServers, detail.hookCount),
        )
        val installed = AgentPluginInstallResult(AgentPluginAuthPolicy.ON_INSTALL, listOf(connector), "Authorize")
        assertEquals(listOf(AgentPluginAuthPolicy.ON_INSTALL, "Authorize"), listOf(installed.authPolicy, installed.message))

        val skillInvocation = AgentInvocation.Skill("review", "/skills/review/SKILL.md")
        val pluginInvocation = AgentInvocation.Plugin("drive", reference.uri)
        assertEquals(
            listOf("review", "skill:/skills/review/SKILL.md"),
            listOf(skillInvocation.name, skillInvocation.key),
        )
        assertEquals(listOf("drive", "plugin:${reference.uri}"), listOf(pluginInvocation.name, pluginInvocation.key))

        assertEquals(
            listOf(AgentMcpEnvironmentSource.LOCAL, AgentMcpEnvironmentSource.REMOTE),
            AgentMcpEnvironmentSource.entries.toList(),
        )
        assertEquals(
            listOf(
                AgentMcpToolApproval.AUTO,
                AgentMcpToolApproval.PROMPT,
                AgentMcpToolApproval.WRITES,
                AgentMcpToolApproval.APPROVE,
            ),
            AgentMcpToolApproval.entries.toList(),
        )
        assertEquals(
            listOf(
                AgentMcpToolExposureSurface.CODE_MODE,
                AgentMcpToolExposureSurface.DEFERRED,
                AgentMcpToolExposureSurface.DIRECT,
            ),
            AgentMcpToolExposureSurface.entries.toList(),
        )
        val environment = AgentMcpEnvironmentVariable("TOKEN", AgentMcpEnvironmentSource.LOCAL)
        assertEquals(AgentMcpEnvironmentSource.LOCAL, environment.source)
        val mcpServer = AgentMcpServer("server", "Server", AgentMcpAuthStatus.NOT_LOGGED_IN)
        assertEquals(
            listOf("Server", AgentMcpAuthStatus.NOT_LOGGED_IN),
            listOf(mcpServer.displayName, mcpServer.authStatus),
        )
        assertEquals(9876, AgentMcpOauthConfiguration("client", 9876).callbackPort)
        assertEquals(AgentMcpToolApproval.APPROVE, AgentMcpToolConfiguration(AgentMcpToolApproval.APPROVE).approval)
    }

    @Test
    @CoversApi(
        "api-v1:AgentAuthenticationState#property:deviceUserCode#sha256:0cdd227e00e5af6d51a3378aabaa9025ac34c660db62952258414990081bce5c",
        "api-v1:AgentAuthenticationState#property:deviceVerificationUrl#sha256:f9995c9c35bd05cafd2a2c9b45c7495a1d9840e711a039a4e0a7045cd1426c61",
        "api-v1:AgentIntegration#property:displayName#sha256:44185b1ee53d1d9a8249e3a434def72b60f1d3f9f8b77ecc30b9d6a20948475d",
        "api-v1:AgentIntegration#property:id#sha256:60e7d6791abc1c7d3a97acf688fe7a3617fef7b8646c8fcb77a8f84a2be2ca64",
        "api-v1:AgentIntegration.Connector#property:displayName#sha256:5bdb71284fb77d3c1f49cdb68e2ae1958dc62a8b8fc8b58326e2a402ad599ca3",
        "api-v1:AgentIntegration.Connector#property:id#sha256:9b63a071b4922e58041061f9e9293a231cd95fff865d5df79be6583a72634fa5",
        "api-v1:AgentIntegration.McpServer#property:displayName#sha256:26ef69b79d3940d51f3f555c4a1c63723e730b0cf7eaf4b2e79207c998b59170",
        "api-v1:AgentIntegration.McpServer#property:id#sha256:e5a164bf61be5d223b011057deddaac89ec9e128c78eea2f80a5e1716e038317",
        "api-v1:AgentPendingApproval#property:title#sha256:d687792a711c67179fb61fb357730e048c6d085ba5391e85914eca107fbf5858",
        "api-v1:CodexAuthorizationPurpose#enum-entry:CHAT_GPT#sha256:8e0930017e9d40bcbe55109d89f71962e2857b09c154f3618663ac650a3fba7b",
        "api-v1:CodexAuthorizationUrl#property:purpose#sha256:a7320decaae7cafc1ee037ab0aa07b559873657c135d0b4f784ae346cf1b0da4",
    )
    fun controllerStateValuesExposeEverySupportedFieldAndVariant() {
        val chatGptUrl = CodexAuthorizationUrl.chatGpt("https://auth.openai.com/authorize")
        val deviceUrl = CodexAuthorizationUrl.external("https://example.com/device")
        assertEquals(
            listOf(CodexAuthorizationPurpose.CHAT_GPT, CodexAuthorizationPurpose.EXTERNAL),
            CodexAuthorizationPurpose.entries.toList(),
        )
        assertEquals(
            listOf(CodexAuthorizationPurpose.CHAT_GPT, CodexAuthorizationPurpose.EXTERNAL),
            listOf(chatGptUrl.purpose, deviceUrl.purpose),
        )
        val authentication = AgentAuthenticationState(
            status = AgentAuthenticationStatus.AUTHENTICATING,
            pendingSignInUrl = chatGptUrl,
            deviceVerificationUrl = deviceUrl,
            deviceUserCode = "ABCD-EFGH",
        )
        assertEquals(
            listOf(deviceUrl, "ABCD-EFGH"),
            listOf(authentication.deviceVerificationUrl, authentication.deviceUserCode),
        )
        val apiKey = CodexAuthenticationMethod.ApiKey("sk-test")
        assertEquals("sk-test", apiKey.value)
        assertFailsWith<IllegalArgumentException> { CodexAuthenticationMethod.ApiKey(" ") }

        val conversationId = ConversationId("conversation-1")
        val approval = AgentPendingApproval("approval-1", conversationId, "Approve", "Details")
        assertEquals(listOf(conversationId, "Approve"), listOf(approval.conversationId, approval.title))
        val elicitation = AgentElicitation("elicitation-1", "server", conversationId, "Choose")
        val pendingElicitation = AgentPendingElicitation(elicitation)
        assertEquals(
            listOf("elicitation-1", conversationId),
            listOf(pendingElicitation.requestId, pendingElicitation.conversationId),
        )
        val interaction = AgentInteractionState(pending = listOf(approval, pendingElicitation))
        assertEquals(listOf(approval, pendingElicitation), interaction.pendingFor(conversationId))

        val connectorIntegration = AgentIntegration.Connector(AgentConnector("drive", "Drive"))
        val connectorTarget: AgentIntegration = connectorIntegration
        assertEquals(
            listOf("drive", "Drive", "drive", "Drive"),
            listOf(
                connectorTarget.id,
                connectorTarget.displayName,
                connectorIntegration.id,
                connectorIntegration.displayName,
            ),
        )
        val serverIntegration = AgentIntegration.McpServer(
            AgentMcpServer("mcp", "MCP", AgentMcpAuthStatus.NOT_LOGGED_IN),
        )
        val serverTarget: AgentIntegration = serverIntegration
        assertEquals(
            listOf("mcp", "MCP", "mcp", "MCP"),
            listOf(serverTarget.id, serverTarget.displayName, serverIntegration.id, serverIntegration.displayName),
        )
    }

    @Test
    @CoversApi(
        "api-v1:AgentElicitation#property:conversationId#sha256:772355d9ca5856a7100438aaab853c6d04acd74752790b25fa68662ac1ceea85",
        "api-v1:AgentElicitation#property:message#sha256:5df4ebba37affd91c5a443de146a2f826d97909cad52e64ab6b7564c17b8723d",
        "api-v1:AgentElicitation#property:requestId#sha256:043bf8d5e75c2cc53978cf98e9c30a533d4e2fd28c298119324b759043827690",
        "api-v1:AgentElicitation#property:serverName#sha256:b6984afc30b8c60bb6b3c5ff47b394a4f7cf55657630e38958272df7c7fd2c30",
        "api-v1:AgentElicitationValidation#constructor:<init>#sha256:da77876bdca57b08a1c8e857cd2cfa91a48e70221771f17cdf6db09900bce8d9",
        "api-v1:AgentElicitationValidationIssue#constructor:<init>#sha256:f4a877eb4c2e4637a71ae7d2bc99e324984c7feb5a382555f2ab38ec689c640e",
        "api-v1:AgentElicitationValidationIssue#property:fieldName#sha256:7660b40d869be4a01ce59190f32631f46a91d0f005269299241ab3d85f9e593b",
        "api-v1:AgentFormField#property:description#sha256:4dfe2e07b89368008eceb8957d82c5422b8e6c9c89f9a5385ce298a25e474752",
        "api-v1:AgentFormField#property:isSecret#sha256:65d27af256ff689356b4cac3fcc50c27e65649567e3a2b5a03fde4b2da6a85a9",
        "api-v1:AgentFormField#property:title#sha256:a1890ccb42db5625f2b1163d913a223f3cb2ea8f90ec251097745a03b5543d2b",
        "api-v1:AgentFormOption#property:title#sha256:1f0e2cd3164d13068898fe8b48c2314b2d2ed505adf4c4e21e1c83ae4369637e",
        "api-v1:AgentFormStringFormat#enum-entry:URI#sha256:9a584930a997fe4f046a7873cadbaaa42fa5f62cdff80e6c3fc9841ca4e38fe3",
    )
    fun validationValuesExposeEverySupportedFieldAndVariant() {
        assertEquals(
            listOf(
                AgentFormStringFormat.EMAIL,
                AgentFormStringFormat.URI,
                AgentFormStringFormat.DATE,
                AgentFormStringFormat.DATE_TIME,
            ),
            AgentFormStringFormat.entries.toList(),
        )
        val option = AgentFormOption("value", "Value", "Description")
        assertEquals(
            listOf("value", "Value", "Description"),
            listOf(option.value, option.title, option.description),
        )
        val field = AgentFormField(
            name = "website",
            title = "Website",
            description = "Public website",
            isRequired = true,
            type = AgentFormFieldType.STRING,
            options = listOf(option),
            defaultValue = AgentFormValue.Text("https://example.com"),
            format = AgentFormStringFormat.URI,
            minimumLength = 3,
            maximumLength = 100,
            minimumSelections = 1,
            maximumSelections = 2,
            isSecret = true,
        )
        assertEquals(listOf("Website", "Public website", true), listOf(field.title, field.description, field.isSecret))
        listOf<() -> Unit>(
            { field.copy(minimumLength = -1) },
            { field.copy(minimumLength = 4, maximumLength = 3) },
            { field.copy(minimumSelections = -1) },
            { field.copy(minimumSelections = 2, maximumSelections = 1) },
        ).forEach { invalid -> assertFailsWith<IllegalArgumentException> { invalid() } }

        val conversationId = ConversationId("conversation-1")
        val elicitation = AgentElicitation(
            requestId = "request-1",
            serverName = "server",
            conversationId = conversationId,
            message = "Provide input",
            form = listOf(field),
            url = "https://example.com/input",
        )
        assertEquals(
            listOf("request-1", "server", conversationId, "Provide input", listOf(field), "https://example.com/input"),
            listOf(
                elicitation.requestId,
                elicitation.serverName,
                elicitation.conversationId,
                elicitation.message,
                elicitation.form,
                elicitation.url,
            ),
        )
        val issue = AgentElicitationValidationIssue("website", AgentElicitationValidationReason.INVALID_FORMAT)
        assertEquals("website", issue.fieldName)
        assertTrue(AgentElicitationValidation(emptyList()).isValid)
    }

    @Test
    @CoversApi(
        "api-v1:CodexFailure#constructor:<init>#sha256:64c9861a196f37e527186e0919ab27ebf6c343060b0b4f72a97ebd996117a3ee",
        "api-v1:CodexFailure#property:code#sha256:0e355590529ac630f015749573a83c546b84d47366924f762ae9290c798e1e84",
        "api-v1:CodexFailure#property:isRecoverable#sha256:8b3e0cd4535919558e2decfc0de3b49568003332c49069a7389b385f0d027601",
        "api-v1:CodexFailure#property:message#sha256:b0f8435c4128db5e5c4cba0e7ee006f8cf5dd9b6ab7969b66ece1543b8713548",
        "api-v1:CodexWorkspaceResolution.SelectionRequired#property:message#sha256:5df0c7c06533966a2febf648d74fcdbf1e0ddf7bf1fd917aa748507811e716f0",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:ACCESS_REVOKED#sha256:91afb4a1dccd4570d3b36de3a4d68732f874509f41a3fa0d3fe4b004ae73296a",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:INVALID_SELECTION#sha256:8230da72e600010220b5cfa426fdd03ea29de053889689a8ec9ad84d948647c6",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:NOT_SELECTED#sha256:02d58b2519a4d867120d5a8f20c8027d577775a0530096f39f9a7065183cb553",
    )
    fun failureAndWorkspaceValuesExposeEverySupportedFieldAndInvariant() {
        val failure = CodexFailure("offline", "Codex is offline", true)
        assertEquals(
            listOf("offline", "Codex is offline", true),
            listOf(failure.code, failure.message, failure.isRecoverable),
        )
        assertFailsWith<IllegalArgumentException> { CodexFailure(" ", "Message", true) }
        assertFailsWith<IllegalArgumentException> { CodexFailure("code", " ", true) }
        assertFailsWith<IllegalArgumentException> { CodexFailure("code", "x".repeat(501), true) }

        val client = CodexClientInfo("app", "Codex App", "1.0")
        assertEquals(listOf("app", "Codex App", "1.0"), listOf(client.name, client.title, client.version))
        val selection = CodexPathWorkspaceSelection("/workspace")
        assertEquals("/workspace", selection.path)
        assertFailsWith<IllegalArgumentException> { CodexPathWorkspaceSelection(" ") }
        assertFailsWith<IllegalArgumentException> { CodexPathWorkspaceSelection("/work\u0000space") }
        val workspace = CodexWorkspace("/workspace", "Workspace")
        assertEquals(listOf("/workspace", "Workspace"), listOf(workspace.path, workspace.displayName))
        assertFailsWith<IllegalArgumentException> { CodexWorkspace(" ") }
        assertFailsWith<IllegalArgumentException> { CodexWorkspace("/workspace", " ") }

        assertEquals(
            listOf(
                CodexWorkspaceSelectionReason.NOT_SELECTED,
                CodexWorkspaceSelectionReason.NOT_FOUND,
                CodexWorkspaceSelectionReason.ACCESS_REVOKED,
                CodexWorkspaceSelectionReason.INVALID_SELECTION,
            ),
            CodexWorkspaceSelectionReason.entries.toList(),
        )
        val available = CodexWorkspaceResolution.Available(workspace)
        assertEquals(workspace, available.workspace)
        val required = CodexWorkspaceResolution.SelectionRequired(
            CodexWorkspaceSelectionReason.ACCESS_REVOKED,
            "Choose another workspace",
        )
        assertEquals(
            listOf(CodexWorkspaceSelectionReason.ACCESS_REVOKED, "Choose another workspace"),
            listOf(required.reason, required.message),
        )
        assertEquals(workspace, CodexHostState.Preparing(workspace).workspace)
        assertEquals(required, CodexHostState.WorkspaceRequired(required).requirement)
        val failed = CodexHostState.Failed(workspace, failure)
        assertEquals(listOf(workspace, failure), listOf(failed.workspace, failed.failure))
    }
}
