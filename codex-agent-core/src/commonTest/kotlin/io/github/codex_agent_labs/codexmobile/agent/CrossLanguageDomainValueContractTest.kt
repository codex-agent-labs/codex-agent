package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class CrossLanguageDomainValueContractTest {
    @Test
    @CoversApi(
        "api-v1:AgentHookHandler.Agent#object:Agent#sha256:1e177881622b84b29a82000206858c307bef8ac1940611d15c04ac3f0406e984",
        "api-v1:AgentHookHandler.Prompt#object:Prompt#sha256:e2a7fc51b50ab37b41f6682dbedb387f967c34ff5a61dc227605ebb5a78e434e",
        "api-v1:CodexAuthenticationMethod.ChatGptBrowser#object:ChatGptBrowser#sha256:e2e11f2ca07d67eb6da27a6eca5e7b5d4451b2df6c4f553f17f33677f12d06f3",
        "api-v1:CodexAuthenticationMethod.ChatGptDeviceCode#object:ChatGptDeviceCode#sha256:cf47a7f37839b9b0d1d4d2842184866a8c6389bfeee9a315f867c8fe0579ce33",
        "api-v1:CodexHostState.Closed#object:Closed#sha256:d8602f7cf27f5dc2c427d6609275fe7d77e91db491069107dd881b5f7040fa9d",
        "api-v1:CodexHostState.New#object:New#sha256:fc9357dfaebdbc55634d7dff6fb586c9f33db31a07dc69f57c0def084d70b30e",
        "api-v1:CodexHostState.Restoring#object:Restoring#sha256:8c150a1a42c8c6dbf69c7e9fd536584b9c1a81751f43877d1f7cf8198d6d3d04",
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
        "api-v1:AgentApprovalDecision#enum-entry:DECLINE#sha256:db4d1df5ec20f42363a10d2b7a416c5e114a21663f8f70e0b32f4608dade7d56",
        "api-v1:AgentApprovalPreset#enum-entry:ASK_ME#sha256:b21b8e8b5b96f7fcaf0669b5dfe1a7ad225e99032388d072795887645a1c7b3e",
        "api-v1:AgentApprovalPreset#enum-entry:AUTO_REVIEW#sha256:46880d4cb53a4f9f85e09acd87861d3459feb94ea78d88584fbe7d4b95a43841",
        "api-v1:AgentApprovalPreset#enum-entry:NEVER#sha256:2cf8c10728df061acc529887cd937e5c188bdb9fd80f819a7f6bb6894c920499",
        "api-v1:AgentApprovalPreset#enum-entry:STRICT#sha256:da0513a0ca0aaf67cda31eb565ce0f89417fff25717a3f7116d464df2aa53403",
        "api-v1:AgentApprovalPreset#property:displayName#sha256:7ec1b79af5087749ddc0cabda780c56400c17e7d2eb41e6c1d34a0e8ac669686",
        "api-v1:AgentCapability#property:icon#sha256:25ca68a448ebcf0cb1ce7e8dabf5f386f92739789bde021275d2ac77cebda6f5",
        "api-v1:AgentCapability#property:id#sha256:aee87ef78abf8369394a85aef0cc4b7aab2dc8128ab49d3177cb6dae51d38150",
        "api-v1:AgentCollaborationMode#enum-entry:DEFAULT#sha256:e7a82ccb52ea70efb42bb512dfc2ef7616813fd6e0668c6d661f6b3b01c8a3d3",
        "api-v1:AgentConversationSettings#constructor:<init>#sha256:b1cd03431bde6e4eaa6a30d3b8174e1107e8ce0cc4b1901f15436875fe1dade1",
        "api-v1:AgentConversationSettings#property:approvalPreset#sha256:f1e5c406c7d28f25c21ddf47f18be5fb8911fe1c5c898dfb79fb5f9a655f0960",
        "api-v1:AgentConversationSettings#property:serviceTier#sha256:910a6f6ca93aecde285d08a79e85f760ae33e2be763f50976ba8f177c12b1bc0",
        "api-v1:AgentConversationSummary#constructor:<init>#sha256:007d8e453c7af3964821b9080d463b6b6591f8e2fc9d88055b4c3d7b776c268c",
        "api-v1:AgentConversationSummary#property:conversationId#sha256:c6d4a5b93eb07a156603a4fd2818c0c743122247b717bc14b068db480213cf98",
        "api-v1:AgentConversationSummary#property:updatedAtEpochSeconds#sha256:e73d71c4caea731dee0b6e726f282f95f894de4278b2de4a91d5cfca763e767d",
        "api-v1:AgentHook#property:currentHash#sha256:9fccab5c1fbf70c83ff2f6cc268b84ab1c1fe20eca4f9f8a872bec61793829aa",
        "api-v1:AgentHook#property:eventName#sha256:3fa83f3a4631741e873a29037e471f72782d02bb7d42328c6e3629976c59cf5a",
        "api-v1:AgentHook#property:handler#sha256:20d43afcbeb501893facd78236583f561496cb7722e168926e0d1f05561eaba8",
        "api-v1:AgentHook#property:isEnabled#sha256:535483f8ab831e688423a0805321c149a64126cce3e9a4f3d5f62e3b45677398",
        "api-v1:AgentHook#property:isManaged#sha256:80695c98b5163152f9be8da2ab04b0b5c1ae66dbb301ca6068039906cca1f64f",
        "api-v1:AgentHook#property:matcher#sha256:a7b8234303d18457e1a9511f98ebe11ac9709ea583e5e4057bf64895dca24f40",
        "api-v1:AgentHook#property:pluginId#sha256:cac4b58e8a7846310cd844eb960ca32527630bf086ee2932ba0281d2fcec1f76",
        "api-v1:AgentHook#property:source#sha256:d0b50845e669d86c0dd6200e0d8883321b5ad058e8700b4ee1034af822391446",
        "api-v1:AgentHook#property:statusMessage#sha256:143adae940a436406226f549fd26b12d766afca9be93a5d5347fe7cbba73afd5",
        "api-v1:AgentHook#property:timeoutSeconds#sha256:311299965b2bcb479325c1cec4d0fdaa4d1be9f0dda66cb96b556d200a71a20c",
        "api-v1:AgentHook#property:trustStatus#sha256:6b812ad95efe296f6be764ce3dfce4f158509166d0e783d0d1d9aa79532c4c0a",
        "api-v1:AgentHookActivity#property:details#sha256:75f62106a714bb4120a2c94dbbed391ef4d1af65fc462000b51d6efbe772b763",
        "api-v1:AgentHookActivity#property:eventName#sha256:4972f6451fe7a2922e555c1764251804e7d715b99c1269ba6eab11c95010c5f8",
        "api-v1:AgentHookActivity#property:handlerType#sha256:f9a483a4d4f855d89ac5773b792f4dcb9dd0e7a7fc86d9997c7eb4308421309e",
        "api-v1:AgentHookActivity#property:statusMessage#sha256:b0dc45272165d9603c9009f89a5b491374fb772b054d949eabf0d8e74ec4ad74",
        "api-v1:AgentHookActivity#property:status#sha256:6525d0ab23b58e81d4da0c4837c03c489b7dc3c49d9c4dea4912639cee9b62a9",
        "api-v1:AgentHookCatalog#property:errors#sha256:fbf26b6e891434858ee770d09e67af1e0d70ce1eb9afe1b6e72c273364f086e5",
        "api-v1:AgentHookCatalog#property:warnings#sha256:5007b4bbf3caf83a14827b3961e848b45430e49ca77ba47c2efa234b5a1808f3",
        "api-v1:AgentHookHandler.Command#constructor:<init>#sha256:6d507d3bd0d51787dba8acde29e67888620d929be5a7eb7046ce47e15518f357",
        "api-v1:AgentHookHandler.Command#property:command#sha256:89433ed2568f7f77988670ebdc600d6613f4013c30cac7d2dc3d158d2846a498",
        "api-v1:AgentHookHandler.Command#property:isAsync#sha256:1d9c3058b5faaacd8b40a2ca38ee9da9b3092d38d84461e9597bc9a8a4e3fa4f",
        "api-v1:AgentHookHandler.McpTool#constructor:<init>#sha256:57c7a38cf05f78c6680f5ba91dd97446af3c5d7a982ed3e4116ee13197867c82",
        "api-v1:AgentHookHandler.McpTool#property:server#sha256:de185078a1a8848743f5478504a658ecef836fb55bcbc1b39a16d1c2bb234e4c",
        "api-v1:AgentHookHandler.McpTool#property:tool#sha256:79a074c5c9009ea4799f63e15ae9c812ffa706bfa37edba5367d9d3861720fae",
        "api-v1:AgentHookRunStatus#enum-entry:BLOCKED#sha256:3ea56135cd6ffd980fc5654b3517bf803f6b78d76781571148ab256f1051f0b5",
        "api-v1:AgentHookRunStatus#enum-entry:COMPLETED#sha256:e40dece7011ea41bd033a0640106625699c229afd824ee1d2ede0a7622f7be28",
        "api-v1:AgentHookRunStatus#enum-entry:FAILED#sha256:93337d14eeddcf4e46adf64d70cdd4fa64d5778bbb482534db45a1d7d1272326",
        "api-v1:AgentHookRunStatus#enum-entry:STOPPED#sha256:94be2a09aa29cb08af9e22cf4c3490a522fa26c89014f3d5b871c4692fc7aab0",
        "api-v1:AgentMessage#property:collaborationMode#sha256:c97901581bd27761fe308e14081bfbb2ab13872a9c8035c04eede06be27ec122",
        "api-v1:AgentMessage#property:invocations#sha256:9b19e5360ab7471874348c45abac352d49b803c08b1f865a50118a1a66d99812",
        "api-v1:AgentMessage#property:plan#sha256:f9cd866f1d0a3520996c97c9ad3350dfaf8ee7575ab2e5bb05d14ba542a96302",
        "api-v1:AgentModel#property:description#sha256:4b512d75f5f8347718a8733ff4ed2e156d1196a507146d439b83d485d5e1e14c",
        "api-v1:AgentModel#property:displayName#sha256:c46ed73adca77efb5c19307db0951da3163633711457e6b939b83cf9f8b03806",
        "api-v1:AgentPlanProgress#property:explanation#sha256:679f20a226204b39570788024e9b9e0b78c0f4968fa13e3d47879352dddcd6bd",
        "api-v1:AgentPlanStep#property:status#sha256:e2d55b9264ca58e537e80d9c1285075cbb584282e27e2269d5050392f54bdbf4",
        "api-v1:AgentPlanStepStatus#enum-entry:COMPLETED#sha256:2ca6ac2a37dee94ddee8e389546584f9aa1b471989b46e2e12054873eb4143ba",
        "api-v1:AgentPlanStepStatus#enum-entry:PENDING#sha256:b64c8b5e8f9b4d3de6be7bef9f2448e77ecfdd44e46746a97bf6dca7a2dafff3",
        "api-v1:AgentServiceTier#property:description#sha256:916ca7c227c86580e13399a218a11225537b05a2d1971babe90ab87763135fe7",
        "api-v1:AgentServiceTier#property:name#sha256:92a4fb5c4b645fe521cfb1fc700a4fd8ef7fc93ed7dda255de5f2e9a5e6f2de3",
        "api-v1:AgentTurnRequest#property:approvalPreset#sha256:fc8fdf1e1623b1212642c20d4339e5275fbee7dfc038a68278f2eb8216e42ef7",
        "api-v1:AgentTurnRequest#property:serviceTier#sha256:237c4f0cc465a4d3023838eb90ff27b949564533ef8e6d238ef6c084b4d9c12a",
        "api-v1:AgentWorkActivity#enum-entry:RUNNING_COMMAND#sha256:788c603635e5b26cd833010b38a8a406cafbbee83b85b180dea72e91d30fea27",
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
        "api-v1:AgentConnector#constructor:<init>#sha256:0167359ac6ee0f4983809cd2aef626eaa9c4543040c9654df4ca1dc1470a4c70",
        "api-v1:AgentConnector#property:description#sha256:6202f5e192ae0d42994e2d78773d69b975f7ce16d6f469acd9086faff8d5672b",
        "api-v1:AgentConnector#property:installUrl#sha256:36535126998e740ced6c47f701a6dc8353d8105d6e97c44748d1df25d13b7dbf",
        "api-v1:AgentConnector#property:isEnabled#sha256:63d406c5d8085946feb2ae6a44e6d1c55cd71c7526af514f0cb36b09c2c38cac",
        "api-v1:AgentConnector#property:name#sha256:3ac03ee539e32a74c4392949593f215d023c246f3c82f690fbf881b779b4a2dd",
        "api-v1:AgentConnector#property:pluginNames#sha256:297f888ee4828f5ce1542d755807b3675cad3592a3d372931c9b04c1674ef9af",
        "api-v1:AgentMcpEnvironmentSource#enum-entry:LOCAL#sha256:40057398186ec13d19eb3fc39bc9c1049a83d95baaf69b91e2ae6af4f15216cb",
        "api-v1:AgentMcpServer#property:authStatus#sha256:4c9ac04c4bb4a94db76620e886c9197ec6045f96e3b114bf0096e6baea44fc31",
        "api-v1:AgentMcpServer#property:displayName#sha256:bcde730028aecff9ceddb14682e37f0add4890cc613b8058956b61feafa373f2",
        "api-v1:AgentMcpToolApproval#enum-entry:APPROVE#sha256:b3391049f0ce2a4d4c0e111f17033d3f8b5d1c6d93e47ab118f77573b9aa448d",
        "api-v1:AgentMcpToolApproval#enum-entry:AUTO#sha256:5ae15ac21b4615785aa9f3c49c5cd080a343b6763ea05ef2705b25db531a30fe",
        "api-v1:AgentMcpToolExposureSurface#enum-entry:DIRECT#sha256:3b5a4457cec0e266d6c1d9f64e2fe95438a7c01c12c551eed98965d590107498",
        "api-v1:AgentPluginDetail#constructor:<init>#sha256:68d7d304e7c1e8aab22064e67d27f5e3c430634248f43022301fbc13f141da5f",
        "api-v1:AgentPluginDetail#property:description#sha256:d878874aefbf285210892f24e3f373a25e46be6a4710e0c82494d729c5f39d19",
        "api-v1:AgentPluginDetail#property:hookCount#sha256:4c1c2e30dfd3763463a6d4c68a5177d9f013e57ed1f58567b08e2a89c8e56f06",
        "api-v1:AgentPluginDetail#property:mcpServers#sha256:a7868b10314a0fe2b6261289c6b24092cf8ce2cde05bef9e7d60b8eb69b532d0",
        "api-v1:AgentPluginDetail#property:skills#sha256:7074952adf2cac7e09601a65422db89534641a4e13ac5bcc51adb9df87b74e55",
        "api-v1:AgentPluginDetail#property:summary#sha256:66f05ac200f50b6fa2e57bab25b51fd4556c15f8d5254c0033c4a9c529770128",
        "api-v1:AgentPluginInstallPolicy#enum-entry:NOT_AVAILABLE#sha256:fb9744d3f80201095105b91721c2b018c8d4d4b84d89f0eb11b2cde8c5d157c3",
        "api-v1:AgentPluginInstallResult#constructor:<init>#sha256:a1131465567b5d55c1a77422e726259962c26e0aaf36dd7a5edf4b34d7e8df0c",
        "api-v1:AgentPluginInstallResult#property:authPolicy#sha256:b97e1e1b63a4723272da82e016ef07a18272d72e0b1e67dfaadecf132b78f26f",
        "api-v1:AgentPluginInstallResult#property:message#sha256:d6161704f7d603c94e6ab69bcb6dfa4b562b69090479056999f29d46c444a6ce",
        "api-v1:AgentPluginReference#property:marketplaceName#sha256:edc7edd756a4a10cd16bd71872b2b154a8e413eea67ec98e4f665d748d0193e0",
        "api-v1:AgentPluginReference#property:marketplacePath#sha256:013062926a854fb8a341a8a0e2b98bd2382ecb73e619465b5ad78cf106da09a3",
        "api-v1:AgentPluginReference#property:name#sha256:67b123fec77ca2d97eca21404eae41135f8425fae8c6ba6813a40c4426a52da6",
        "api-v1:AgentPluginReference#property:uri#sha256:807a011a9578c5ff0f4ca5fdf6e5bc100bf658b9fb5fda2ded116f2085af5cc7",
        "api-v1:AgentPluginSkill#constructor:<init>#sha256:f03ddd0f2ceee24cfc4ef4f1bdfb400602b77c9750827635e5095f6bab665f48",
        "api-v1:AgentPluginSkill#property:description#sha256:c6693319a86aa9bd123e5553b65ee3b320e45250ce85c7dd5e459cba9486275f",
        "api-v1:AgentPluginSkill#property:isEnabled#sha256:de343810af133c80b886208390738056a472dfe384d46e60c5afa95379040478",
        "api-v1:AgentPluginSkill#property:name#sha256:9ce639fbd9d6dd6cedab5f8df7a750dbac9c30f2cf10a37a5fdfdd72382e0c1d",
        "api-v1:AgentPluginSkill#property:path#sha256:291d2b676cfddc511b0e4f478a2cc79213ac490d6cd49e453071d3287df4d482",
        "api-v1:AgentPluginSummary#property:brandColor#sha256:afe2eec4834829d980991e36b54a76761846b72d1fd32b94c00fd8268b6f0243",
        "api-v1:AgentPluginSummary#property:capabilities#sha256:4352e2de8780e4a8af0775bde179d5df860361806fa294e62895dc8b5d79765e",
        "api-v1:AgentPluginSummary#property:isAvailable#sha256:7a8b3c1461f709053ffb5c3948bc45bea31251339ca9bd239924d27cae2afb8a",
        "api-v1:AgentPluginSummary#property:privacyPolicyUrl#sha256:66589d63dbb468fe103cb37fb5b461fdad6e12b9e65d08562604f5151308e0c4",
        "api-v1:AgentPluginSummary#property:termsOfServiceUrl#sha256:2b97b6b2b7ba9370e6e28d91f20841e55de81ec068bda92333969e21c74e34ff",
        "api-v1:AgentPluginSummary#property:websiteUrl#sha256:577b7110ca3ff3d4abdf7c5d69416c464ec9661f2dc91bee7cd1ccd0abeb50d6",
        "api-v1:AgentResourceOrigin#enum-entry:MANAGED#sha256:f20e65f0795882ed9ee1b8d6fbb09e2ec7989733784ad05ccb8b05a08e1a6f33",
        "api-v1:AgentResourceOrigin#enum-entry:PLUGIN#sha256:524d68522570f3480ba699d22ccc6dc884ff427f1d17aafdf32cf74a59e3976a",
        "api-v1:AgentResourceOrigin#enum-entry:UNKNOWN#sha256:a2e5acda22357e08a60655a0c99af598f6c0bc80472606c7612200b4d09b0932",
        "api-v1:AgentSkill#property:brandColor#sha256:f9c6ecb48555360bcdc284937636f434313a97fcb254800741853d652bc94f00",
        "api-v1:AgentSkill#property:dependencies#sha256:72a26ced5d1966c6146abc0c5e9f924ead24945e43abf13b93c084de1b9811b4",
        "api-v1:AgentSkill#property:description#sha256:1b96865137416a281c2d7cbeb87cf7a5cea5da3aa6a4fe37627427d209e464fd",
        "api-v1:AgentSkill#property:displayName#sha256:0d4f1ed49331123279cea9cf95398167c931c79b83e004325b1256633ff70f5a",
        "api-v1:AgentSkill#property:isEnabled#sha256:39ff6ec5cc6764d93cfaafb395557cbeb88f9572b5c1450877e1d016c2b2f58e",
        "api-v1:AgentSkill#property:scope#sha256:f77f6ef46837a012070c6d5aa442043bff4511d150b3e7116d57411ca593ce49",
        "api-v1:AgentSkillCatalog#property:errors#sha256:0057707440406a23a778fe9bd5789cd86eebf1a714a34b81133854f6cda3417a",
        "api-v1:AgentSkillChunk#constructor:<init>#sha256:c975dd08b56bd5b44cbe6ce34f7d865975e2f6cfe02e3c15e96c4fa3f36a8d50",
        "api-v1:AgentSkillChunk#property:totalBytes#sha256:0cf79c67df899fe46e0892341450e615367bac331dcc87d91a005fb5a92b1152",
        "api-v1:AgentSkillScope#enum-entry:ADMIN#sha256:9b60bc297dfaba5766c022a2373bf1b5b13f516ef3637d85f39698651f7facd7",
        "api-v1:AgentSkillScope#enum-entry:PLUGIN#sha256:6b5dbf9f4d31d4f5e5e4338503ff04d51f18983fc24bba480731fe4db041f453",
        "api-v1:AgentSkillScope#enum-entry:SYSTEM#sha256:643ff6404fb3bd033d685ea55d3ca637ff007aa6421193cdf098c28ad012337f",
        "api-v1:AgentSkillScope#property:displayName#sha256:cfac4b0ce2e077716cb2516b045f6feac811edf04856cb7da2cc07742dd2cf69",
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
        "api-v1:AgentAuthenticationState#property:deviceUserCode#sha256:404ec2cf06f874b03b3bf8f65a7ee3d91670644a30951e26cd01574a877f198a",
        "api-v1:AgentAuthenticationState#property:deviceVerificationUrl#sha256:7a2c1af3419c46dfbeec0dd822ce94d6092eaffa7e265162b55d02ccccda16b0",
        "api-v1:AgentIntegration#property:displayName#sha256:cd22679cca61e6138cc79bfbd515958abefb9bc4f9cdb7bfe4c54d38a5491361",
        "api-v1:AgentIntegration#property:id#sha256:adaca37cf37c11746c2ed8ea37f61bde43de0fe9777d4ba7d332b25bf63b354e",
        "api-v1:AgentIntegration.Connector#property:displayName#sha256:0f8d45b3c7d586afb2c24e1b0f2eb85a6373d705d001284b8f34f33c540bd9bd",
        "api-v1:AgentIntegration.Connector#property:id#sha256:f58e7210ee522983b352a3d03ae1f7a66ddb614e1a978a223474ffe9b48d8718",
        "api-v1:AgentIntegration.McpServer#property:displayName#sha256:2c75560f80cf9bb13ac7f5bd8b471565f24df464dec01ce95659f351e7730c77",
        "api-v1:AgentIntegration.McpServer#property:id#sha256:82dc19a8e0c3f9f441e58a078af5fdf3331f091c3c01e1aee426645f11e5b66e",
        "api-v1:AgentPendingApproval#property:title#sha256:edb77e1f55ce7f671f84a095c611dfe6cbb01c0c86d7110952fe8aa7955f4ae2",
        "api-v1:CodexAuthorizationPurpose#enum-entry:CHAT_GPT#sha256:3b50d120b02d5f8ef0204814ba12e063743b5dbccb8120790a406c1a86c76eed",
        "api-v1:CodexAuthorizationUrl#property:purpose#sha256:ad9f8292f5c5662bbc8c45812a44fa4b68150ed3dbc2288af271c5726f738d24",
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
        "api-v1:AgentElicitation#property:conversationId#sha256:c8a0a9fc3e2434a16a389c82072891bc015f328af19a7e461fbf1ba6f6255dcb",
        "api-v1:AgentElicitation#property:message#sha256:b479c232c804408f89f25575bf040d809b670727ab948ce49e48fa22e7d0c3e5",
        "api-v1:AgentElicitation#property:requestId#sha256:c3fe9d2d18afb6921a1d9913de6800854471847e3ca5b93aa471ae0ea98d5701",
        "api-v1:AgentElicitation#property:serverName#sha256:78af05f116f0cbeb743ebc88747ba4d9192c24c2a9beeb6e43c764a57dab1cfa",
        "api-v1:AgentElicitationValidation#constructor:<init>#sha256:7f49f01c8a60cb7a209c87319ff01da0d361f5506f5dfc72765ad9d077bf68b0",
        "api-v1:AgentElicitationValidationIssue#constructor:<init>#sha256:51bcb6f59aecf4827627021b892ddffc31f6ed68f8e488fcbedc97a3f3031f4c",
        "api-v1:AgentElicitationValidationIssue#property:fieldName#sha256:8195f7772a4ff590df7667dd91b43de5340a011d765eaba5ac5d96c0af585a65",
        "api-v1:AgentFormField#property:description#sha256:829bdf8b5ede619b48e40a20f9f5fc4775dda4a4d29151deb267aad3e20dd3ef",
        "api-v1:AgentFormField#property:isSecret#sha256:ee2d2eaa7f785f7a2de12578ea5d1f203cc29c46a5974e2e0fafcb2861894002",
        "api-v1:AgentFormField#property:title#sha256:df6b79f8b18733fc3c2c2779d8290d61f6a05b87c0a2658b0f902b657638c4a6",
        "api-v1:AgentFormOption#property:title#sha256:dd0334c2d4285f0844d5ee1a101d26456baf0ce6cb9941c082e1b62a24215e8e",
        "api-v1:AgentFormStringFormat#enum-entry:URI#sha256:ad4748d694f28e6094d2ec5b198d94963b47c9785d0c497ca67adbac81180ab9",
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
        "api-v1:CodexFailure#constructor:<init>#sha256:db9872249097654acec4959fcef85fbac47c20419b28bbceee4a2ed40f619dce",
        "api-v1:CodexFailure#property:code#sha256:3a601436ff450cdd3e651dfc2e9faf56278431319e63c16c5fc2bff9417f10f9",
        "api-v1:CodexFailure#property:isRecoverable#sha256:8973cb954621824ea55abdabe7aa39d7b8db93b56057971121255b2e7bd0cfa6",
        "api-v1:CodexFailure#property:message#sha256:8bc0e280b734d05df8b06e7f8f5544ba9323faa14cd59b35531b05ea3023ddad",
        "api-v1:CodexWorkspaceResolution.SelectionRequired#property:message#sha256:975ab5d03b64c63678109f3e47ab49255a86a6cb1b8fbf6eae22051847a63585",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:ACCESS_REVOKED#sha256:b603d82d306d0e2d95ce4ce65c28a5faf80aaf0a4e410cda60c3c8edf299781c",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:INVALID_SELECTION#sha256:faea337054ff71946cd8c31074ec7e55bb3b9dbe7c5c7ab8eca865cf78966c64",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:NOT_SELECTED#sha256:d8fb81a0690742ff61ed993687b8f3651e6159c961c12c615f712a9d81a58a6f",
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
