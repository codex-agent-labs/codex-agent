package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CodexPublicApiAdoptionTest {
    @Test
    @CoversApi(
        "api-v1:CodexClientInfo#constructor:<init>#sha256:fdd1cabd3ed693fedc5b54a4389905b90ec2f9080e3874bc4460a67128553108",
    )
    fun clientIdentityRejectsBlankAndControlCharacters() {
        assertFailsWith<IllegalArgumentException> { CodexClientInfo("", "App", "1") }
        assertFailsWith<IllegalArgumentException> { CodexClientInfo("app", "App\nName", "1") }
        assertFailsWith<IllegalArgumentException> { CodexClientInfo("app", "App", "1\u0000") }
    }

    @Test
    @CoversApi(
        "api-v1:AgentConversationState#constructor:<init>#sha256:b95bb1f585879ce700923aa227494b46e7eb35781b759f4c4e2396480c2e96fd",
        "api-v1:AgentConversationState#property:canCancelTurn#sha256:6a706fb51904e93f75458594bad565ed1c40c47a30a409f9d6f9bce7f20fa6db",
        "api-v1:AgentConversationState#property:canReload#sha256:7123617d61c37ca32ea6e3710b68ec0c98276625e2b9849f952278af4a8c1a10",
        "api-v1:AgentConversationState#property:canStartTurn#sha256:84affae02877c0cd94edb1b3efe46ccd38a4e4e0c6d6820c87a110d79c37cad3",
        "api-v1:AgentConversationStatus#enum-entry:CANCELLING_TURN#sha256:1e8f051e9dda2618f8d6cb61cdd8c0c5b9f8805012ef6b8c475bc13eed1b8844",
        "api-v1:AgentConversationStatus#enum-entry:CLOSED#sha256:810b187e91c6c02b66f21203ab22c3c7b0afc8d32996c417a3f205e34cada80d",
        "api-v1:AgentConversationStatus#enum-entry:FAILED#sha256:5bbfe5d1448aa7baec3514eec1b858577de4402c49ea3af63e4ecd6ee42f0b1c",
        "api-v1:AgentConversationStatus#enum-entry:NEW#sha256:449d52d771feb2f815d72eb62de1e1734d8aae6b2e9e5a811e62774d7c36582d",
        "api-v1:AgentConversationStatus#enum-entry:OPENING#sha256:b0fc8d5af7d148fa0a210e3a777c27807b2291285045e116548a1c8a32284f20",
        "api-v1:AgentConversationStatus#enum-entry:READY#sha256:fd58f381925f087488237664778f7ead31f4a057067bac425c21e8b21abc486a",
        "api-v1:AgentConversationStatus#enum-entry:RELOADING#sha256:69cc5178e25cb63ba9462c5ebb5f740ea24384b234a88aebbef033850427dae0",
        "api-v1:AgentConversationStatus#enum-entry:RUNNING_TURN#sha256:1360b2dc72430b9be95686db185de99f499f9814a72b3e0ab870bc1f47db0a28",
        "api-v1:AgentConversationStatus#enum-entry:STARTING_TURN#sha256:fc08e13393b9aee6768835c31cd71c907975865ef9d9a59e73697d5b496a97b4",
    )
    fun conversationCapabilitiesCoverEveryStatus() {
        AgentConversationStatus.entries.forEach { status ->
            val ready = status == AgentConversationStatus.READY
            val recoverable = status == AgentConversationStatus.FAILED
            val state = AgentConversationState(
                status = status,
                conversationId = ConversationId("thread-1"),
                failure = CodexFailure("test", "test", recoverable).takeIf { recoverable },
            )
            assertEquals(ready || recoverable, state.canStartTurn, status.name)
            assertEquals(ready || recoverable, state.canReload, status.name)
            assertEquals(
                status == AgentConversationStatus.STARTING_TURN || status == AgentConversationStatus.RUNNING_TURN,
                state.canCancelTurn,
                status.name,
            )
        }
        assertFalse(AgentConversationState(status = AgentConversationStatus.READY).canStartTurn)
        assertFalse(
            AgentConversationState(
                AgentConversationStatus.FAILED,
                ConversationId("thread-1"),
                failure = CodexFailure("test", "test", false),
            ).canStartTurn,
        )
        assertTrue(
            AgentConversationState(
                AgentConversationStatus.FAILED,
                ConversationId("thread-1"),
                failure = CodexFailure("test", "test", false),
            ).canReload,
        )
    }

    @Test
    @CoversApi(
        "api-v1:AgentHook#constructor:<init>#sha256:ebdb4f13688d0eef21e5e9dd404e625d9634a177bec1e6b23450a6457ce0dfd7",
        "api-v1:AgentHook#property:canTrust#sha256:51d08e56411f6233632851a23624f0afa9c8d19db4e3d8441f9cdff682806cce",
        "api-v1:AgentHookTrustStatus#enum-entry:MANAGED#sha256:68259cffbabc24ccfecf06145d1c848f17750fb25490f2c0f6160578316bf0a2",
        "api-v1:AgentHookTrustStatus#enum-entry:MODIFIED#sha256:7c801942b17c190d8d1c9bfba2d725069562d0c255881ce1dcc464ed97a1aedd",
        "api-v1:AgentHookTrustStatus#enum-entry:TRUSTED#sha256:acd56cc3a69816a176a54139496a886c7d3ede8ed74f0346051a89e845ad96d7",
        "api-v1:AgentHookTrustStatus#enum-entry:UNTRUSTED#sha256:4540c1f8167d3bc08c5c6b5ff894415abab4f695327240db8234dc06c7d4740d",
        "api-v1:AgentMcpAuthStatus#enum-entry:BEARER_TOKEN#sha256:44b50b8dfd1ce21ebdb4fb57e6541b18d8c049bc31632e3f99d1f0d09d012aab",
        "api-v1:AgentMcpAuthStatus#enum-entry:NOT_LOGGED_IN#sha256:e72583d60936765eaeb920501947116d602748a896bc83709e33eed83b8c347b",
        "api-v1:AgentMcpAuthStatus#enum-entry:OAUTH#sha256:1c9cba4a0bf6c1081b98ad3a6b3558701b2b09c321509732a5c66fc16484b023",
        "api-v1:AgentMcpAuthStatus#enum-entry:UNKNOWN#sha256:7d58bbc05006008a54b84c67d79e78c41909cde20fca569b402989fa4c1a2084",
        "api-v1:AgentMcpAuthStatus#enum-entry:UNSUPPORTED#sha256:c53cd433bcdf51c0e3ceadea7c4768a27ca1fc066c4d322f12742eec27999a64",
        "api-v1:AgentMcpServer#constructor:<init>#sha256:e80d42df108f76db72a2ba23ed9bc6834b2d94e048254dd5bbd822b415940532",
        "api-v1:AgentMcpServer#property:isAuthorized#sha256:fe777a3e6132fd03063a3c221796048a76fddf0e98532347efdb4a7cfd7cbbb9",
    )
    fun resourceConveniencePropertiesCoverEveryStatus() {
        AgentMcpAuthStatus.entries.forEach { status ->
            val server = AgentMcpServer("server", "Server", status)
            assertEquals(
                status == AgentMcpAuthStatus.BEARER_TOKEN || status == AgentMcpAuthStatus.OAUTH,
                server.isAuthorized,
                status.name,
            )
        }

        AgentHookTrustStatus.entries.forEach { status ->
            val hook = AgentHook(
                key = "hook",
                currentHash = "hash",
                isEnabled = true,
                eventName = "SessionStart",
                handler = AgentHookHandler.Command("echo ready", isAsync = false),
                isManaged = false,
                source = "USER",
                sourcePath = "/hooks.json",
                timeoutSeconds = 10,
                trustStatus = status,
            )
            assertEquals(
                status == AgentHookTrustStatus.UNTRUSTED || status == AgentHookTrustStatus.MODIFIED,
                hook.canTrust,
                status.name,
            )
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentInteractionState#constructor:<init>#sha256:2f20415a7cd63439aa6fdb6a8f0a9a0377383530651884faf19da842eb3a9471",
        "api-v1:AgentInteractionState#function:isResolving#sha256:8d0ba38e171ac977fe042bcc6f26c20e25cc513af33d927eee61d3e39402774b",
    )
    fun interactionResolutionRequiresTheOwnedPendingInstance() {
        val approval = AgentPendingApproval(
            requestId = "request-1",
            conversationId = ConversationId("thread-1"),
            title = "Approve",
            details = "Details",
        )
        val resolving = AgentInteractionState(
            pending = listOf(approval),
            resolvingRequestIds = setOf(approval.requestId),
        )

        assertTrue(resolving.isResolving(approval))
        assertFalse(resolving.isResolving(approval.copy()))
        assertFalse(resolving.copy(resolvingRequestIds = emptySet()).isResolving(approval))
        assertFalse(resolving.copy(pending = emptyList()).isResolving(approval))
    }

    @Test
    @CoversApi(
        "api-v1:AgentElicitation#constructor:<init>#sha256:cf9662bd2ac45ca550019b2e010fc9f2759ca40a83b04c8bdd0fa077b8dd1273",
        "api-v1:AgentElicitation#function:accepts#sha256:8ba4c2f5f4d79b298b491b66e2f950c954cab92f9606e2d2d66c8080500259d6",
        "api-v1:AgentElicitation#function:accept#sha256:c0d272dc1edd62ecd7b7bc8576d3564a469351a04115bcae1b345d61eafa6186",
        "api-v1:AgentElicitation#function:initialValues#sha256:f92358566940f9bbbd56d8e42077d23497dac93ea499d21f34fb9efbe60f4a03",
        "api-v1:AgentElicitation#function:validate#sha256:63cca3f68c3f5cd1c2226e4ed4aa4129b74df7b5a9deacc8498d295d489ed8e4",
        "api-v1:AgentElicitationAction#enum-entry:ACCEPT#sha256:c481b65c165c21a081bfc1ed4f2a6c58e0118dd451e3869b8a80b0a2cf2dcc11",
        "api-v1:AgentElicitationAction#enum-entry:CANCEL#sha256:2247d8fb7ccecf2021557b03d85a9e35917d69767a970690e9e87c0f77dc79cd",
        "api-v1:AgentElicitationAction#enum-entry:DECLINE#sha256:b3fb0b76797e7471af7e95d7f7357fc80c2fa04ceef2e2b8ee368e58bf55c525",
        "api-v1:AgentElicitationResponse#constructor:<init>#sha256:d29f5881ad792d369bd644bf64a81af6e7f10d9e898fa97fc6da5d79953a91ea",
        "api-v1:AgentElicitationResponse#property:action#sha256:05992eb60ebeae70d41d0f1152d1af78aa270d826104f73edc1c564db58f1660",
        "api-v1:AgentElicitationResponse#property:content#sha256:f9210ef8b5b183d9b0bf771df60d1c104257e0d1c4a3acd6d914c06213e8b078",
        "api-v1:AgentElicitationResponse.Companion#function:cancel#sha256:c3ac5ca07683e0811b90bf2463359ff2bf943203b444d9cf2876b3fd6ea52e42",
        "api-v1:AgentElicitationResponse.Companion#function:decline#sha256:e7bb7e967f3af48069b10404e2208fb914da0f1de26958a6932809b9c71c62ea",
        "api-v1:AgentElicitationValidation#property:isValid#sha256:9b1e3fba3df9ce48e30afcdc4f1b090cddb0e9652b675fe8e6f3031b9268dcb1",
        "api-v1:AgentElicitationValidation#property:issues#sha256:45c3d92095e8bd330b9a086e3a9b1336761afb25686cc526f2946880415dfd06",
        "api-v1:AgentElicitationValidationIssue#property:reason#sha256:e5ed0d56cbc1c89822ba4d4ffd20029d5c1dbd9384a5e363c8d7f06ac90df9c9",
        "api-v1:AgentElicitationValidationReason#enum-entry:ABOVE_MAXIMUM#sha256:5c7e1b815c83710d3736589512a85c786eb4f4ea8a0ef7962089f2490b5e4998",
        "api-v1:AgentElicitationValidationReason#enum-entry:BELOW_MINIMUM#sha256:979a4fb3ca5371de43538779b5a7d54aaf26d4147b53a9682ca8fab2c0d1622c",
        "api-v1:AgentElicitationValidationReason#enum-entry:DUPLICATE_SELECTION#sha256:23f0b571e96147f17e1ceba931c5a10e941930917456c98a668b8d7d75c8e3ad",
        "api-v1:AgentElicitationValidationReason#enum-entry:INVALID_FORMAT#sha256:fda73bea3173663fcbf5c8fa8b626b7685ffcd31ccad5530fb2a3c6492f62e37",
        "api-v1:AgentElicitationValidationReason#enum-entry:INVALID_SELECTION#sha256:9eaefa45c72f3385b5659755ce8c8c91ee83a23e5882c98b4999dfaa2ae81284",
        "api-v1:AgentElicitationValidationReason#enum-entry:INVALID_TYPE#sha256:9a5a8558aae0d6af838c92661507cdc142a7a55cc442dd84e1933131925ec7d8",
        "api-v1:AgentElicitationValidationReason#enum-entry:MISSING_REQUIRED#sha256:ac2f43701c35d84b017219911320cc839ea1dd9e9c073cae19af67b97e265227",
        "api-v1:AgentElicitationValidationReason#enum-entry:NON_FINITE_NUMBER#sha256:9ed8172e16140fe3d7d70649570e9dc32191fbe69e2ee63b9bd49ca06e979079",
        "api-v1:AgentElicitationValidationReason#enum-entry:NON_INTEGER#sha256:de3591411af40f69e6424ecd30b20b63c8e1e64990171aafc3d0a1f0699ab99c",
        "api-v1:AgentElicitationValidationReason#enum-entry:UNKNOWN_FIELD#sha256:6b349e240c4fd53809620a1eabd00845517a7bf2818d37a98c127a26f25e17a6",
        "api-v1:AgentFormField#constructor:<init>#sha256:0b99885f2600d03c98585f40760b688318ae6c876c41b68fe1735d250c4b20c2",
        "api-v1:AgentFormField#property:allowsOther#sha256:1534af7ae95a1141bf1007870e2e9101d23cdd6e9f696858a10bb8235db3c0f8",
        "api-v1:AgentFormField#property:defaultValue#sha256:b43e94c234c7f4625a8da82447b361116c4dd32698c55aaf266a87663749fd86",
        "api-v1:AgentFormField#property:format#sha256:da32b5d1c20e2690e0e3cfd1041b50e773b533173f321f11401e23af1f1aea04",
        "api-v1:AgentFormField#property:isRequired#sha256:0b61d59c19120666031a45a49a98cac21964653c1e5c2218e35edd87a704a8b8",
        "api-v1:AgentFormField#property:maximumLength#sha256:04a38b40b996fc3ffadc4edd8a989f9217b6e23679261743bee8ae4cc474f979",
        "api-v1:AgentFormField#property:maximumSelections#sha256:63928cb03a66b2e47ac1fcab509f6fd0723fd20c370fe8c7af1516c2b55affeb",
        "api-v1:AgentFormField#property:maximum#sha256:25477c28e30e72f993eba973ce5a3882866f33b263760fc4e7b5168bc3ccd62a",
        "api-v1:AgentFormField#property:minimumLength#sha256:9db5a3b3e8bf01c9443e297e0364974ed1dbfee889d17065663894e935b9fc82",
        "api-v1:AgentFormField#property:minimumSelections#sha256:97122b459fe73fe4c05abbf62e16a26b47cf130752a79c03c605696169e5c145",
        "api-v1:AgentFormField#property:minimum#sha256:73bd8d8f4e59dd327b6cf3c38e908520492dd450db78d311fdc6ca7dfb8f5f4d",
        "api-v1:AgentFormField#property:name#sha256:80cebf494511792d2bcebc4fdc08df319a2048702999af3a4635130d47cbb645",
        "api-v1:AgentFormField#property:options#sha256:8ed46849b09eabcf6d84b04fde4b7097d47a2676953656e0ee82811d31a031ec",
        "api-v1:AgentFormField#property:type#sha256:5df1e80ecf023dac2ee69b7777db3ea25b9fe666fb15c003b0a3b3c4e3461238",
        "api-v1:AgentFormFieldType#enum-entry:BOOLEAN#sha256:65c0765a32419ffd6a5d3bdcc580be3b146268619c20c7108348d40ab5ba9505",
        "api-v1:AgentFormFieldType#enum-entry:INTEGER#sha256:4c627864a11e5d38c2bcc6982c29a5d2d5d7493b2dc3c1d515a01696fad90850",
        "api-v1:AgentFormFieldType#enum-entry:MULTI_SELECT#sha256:557054dd108843dacf6c85a51354e44779de04f994c63521746e3299ca5a2952",
        "api-v1:AgentFormFieldType#enum-entry:NUMBER#sha256:bd931ffcde038dc0205940be48e10c2e0a587255f423f8724fa6e2bb09852f39",
        "api-v1:AgentFormFieldType#enum-entry:SINGLE_SELECT#sha256:fc2963015442b1745254904f02fd5729a22d0f6f691e52dc14218f719c986e55",
        "api-v1:AgentFormFieldType#enum-entry:STRING#sha256:1ee3d7c1f1f81356a4ad51152ec3d66692142ad597c4955c1abdfdadfdd7c4dc",
        "api-v1:AgentFormOption#constructor:<init>#sha256:2c8c2dd1747e26e034dff4b9db6bed87caab59d76d472e9fbfd6e488212c42a3",
        "api-v1:AgentFormOption#property:value#sha256:2359d75888e8fbbb52e343e42b18030421cfc4f960d7ea9acd83e9de613cedbb",
        "api-v1:AgentFormStringFormat#enum-entry:DATE_TIME#sha256:d06b4552154e8e58f62141f7d22412a06e3dd15517457491de80a86cf278eeaa",
        "api-v1:AgentFormStringFormat#enum-entry:DATE#sha256:82ce14456a1039cbaeafa76a7df564356edf59ec58fee26d36cb24ff684c0bc2",
        "api-v1:AgentFormStringFormat#enum-entry:EMAIL#sha256:9524032512d558a58da9cd71135c5b07676eb03f7590acb270f463e0ffec40ec",
        "api-v1:AgentFormValue.BooleanValue#constructor:<init>#sha256:ba4dbbf961dca60138a90b01cc14645fa9edca4fc46b68832dc5dbfc80ffb8e7",
        "api-v1:AgentFormValue.BooleanValue#property:value#sha256:640c8726b7b53d9845f4e4b08ed50bee51ff7a8d3c75d1f9d34c66cd0a5027bc",
        "api-v1:AgentFormValue.Number#constructor:<init>#sha256:23f8fdcbf37481f215f67d1ea4463901be5a0960d7da812ba96b7fe7b59974dc",
        "api-v1:AgentFormValue.Number#property:value#sha256:b28d23fab557d74452f20536918401859e2d1ef47636b2bb86b3f7da7d3a4503",
        "api-v1:AgentFormValue.Text#constructor:<init>#sha256:5b5a2473564a3c8e8550758f331f57a7f824b314b779e1b9b1aa0a58b4e499fd",
        "api-v1:AgentFormValue.Text#property:value#sha256:54fc56f883e53106a8daf40efabde4c04e226b1ef0d9d8598ae9f8f31441369c",
        "api-v1:AgentFormValue.TextList#constructor:<init>#sha256:881e244857bc4e1ce48b82bea49f689ce704308cdf95d9dee9df0d622b402110",
        "api-v1:AgentFormValue.TextList#property:value#sha256:e35325f387fa78b8cf134b1faeb4e227d3781ee31b80b18931d0c45540181fcf",
    )
    fun elicitationHelpersShareOneValidatorAndSnapshotResponses() {
        val defaultSelections = mutableListOf("a")
        val elicitation = AgentElicitation(
            requestId = "request-1",
            serverName = "server",
            conversationId = ConversationId("thread-1"),
            message = "Configure",
            form = listOf(
                AgentFormField(
                    "name",
                    "Name",
                    isRequired = true,
                    type = AgentFormFieldType.STRING,
                    minimumLength = 2,
                    maximumLength = 4,
                ),
                AgentFormField(
                    "email",
                    "Email",
                    type = AgentFormFieldType.STRING,
                    format = AgentFormStringFormat.EMAIL,
                ),
                AgentFormField(
                    "date",
                    "Date",
                    type = AgentFormFieldType.STRING,
                    format = AgentFormStringFormat.DATE,
                ),
                AgentFormField(
                    "timestamp",
                    "Timestamp",
                    type = AgentFormFieldType.STRING,
                    format = AgentFormStringFormat.DATE_TIME,
                ),
                AgentFormField(
                    "count",
                    "Count",
                    type = AgentFormFieldType.INTEGER,
                    defaultValue = AgentFormValue.Number(2.0),
                    minimum = 1.0,
                    maximum = 3.0,
                ),
                AgentFormField("ratio", "Ratio", type = AgentFormFieldType.NUMBER),
                AgentFormField("enabled", "Enabled", type = AgentFormFieldType.BOOLEAN),
                AgentFormField(
                    "choice",
                    "Choice",
                    type = AgentFormFieldType.SINGLE_SELECT,
                    options = listOf(AgentFormOption("a")),
                ),
                AgentFormField(
                    "many",
                    "Many",
                    type = AgentFormFieldType.MULTI_SELECT,
                    options = listOf(AgentFormOption("a"), AgentFormOption("b"), AgentFormOption("c")),
                    minimumSelections = 1,
                    maximumSelections = 2,
                ),
                AgentFormField(
                    "default_many",
                    "Default many",
                    type = AgentFormFieldType.MULTI_SELECT,
                    options = listOf(AgentFormOption("a"), AgentFormOption("b")),
                    defaultValue = AgentFormValue.TextList(defaultSelections),
                ),
            ),
        )

        val initial = elicitation.initialValues()
        defaultSelections += "b"
        assertEquals(listOf("a"), (initial.getValue("default_many") as AgentFormValue.TextList).value)
        assertEquals(
            listOf("a", "b"),
            (elicitation.initialValues().getValue("default_many") as AgentFormValue.TextList).value,
        )
        assertEquals(AgentFormValue.Number(2.0), initial.getValue("count"))
        assertEquals(
            AgentElicitationValidationReason.MISSING_REQUIRED,
            elicitation.validate(emptyMap()).issues.single().reason,
        )
        assertEquals(
            AgentElicitationValidationReason.UNKNOWN_FIELD,
            elicitation.validate(mapOf("name" to AgentFormValue.Text("ok"), "other" to AgentFormValue.Text("x")))
                .issues.single().reason,
        )

        val invalidValues = listOf(
            "name" to AgentFormValue.Number(1.0) to AgentElicitationValidationReason.INVALID_TYPE,
            "name" to AgentFormValue.Text("x") to AgentElicitationValidationReason.BELOW_MINIMUM,
            "name" to AgentFormValue.Text("abcde") to AgentElicitationValidationReason.ABOVE_MAXIMUM,
            "email" to AgentFormValue.Text("invalid") to AgentElicitationValidationReason.INVALID_FORMAT,
            "date" to AgentFormValue.Text("2026-02-31") to AgentElicitationValidationReason.INVALID_FORMAT,
            "timestamp" to AgentFormValue.Text("2026-01-01T12:00:00+garbage") to
                AgentElicitationValidationReason.INVALID_FORMAT,
            "ratio" to AgentFormValue.Text("one") to AgentElicitationValidationReason.INVALID_TYPE,
            "enabled" to AgentFormValue.Text("true") to AgentElicitationValidationReason.INVALID_TYPE,
            "choice" to AgentFormValue.Number(1.0) to AgentElicitationValidationReason.INVALID_TYPE,
            "many" to AgentFormValue.Text("a") to AgentElicitationValidationReason.INVALID_TYPE,
            "count" to AgentFormValue.Number(Double.NaN) to AgentElicitationValidationReason.NON_FINITE_NUMBER,
            "count" to AgentFormValue.Number(0.0) to AgentElicitationValidationReason.BELOW_MINIMUM,
            "count" to AgentFormValue.Number(4.0) to AgentElicitationValidationReason.ABOVE_MAXIMUM,
            "count" to AgentFormValue.Number(1.5) to AgentElicitationValidationReason.NON_INTEGER,
            "choice" to AgentFormValue.Text("z") to AgentElicitationValidationReason.INVALID_SELECTION,
            "many" to AgentFormValue.TextList(listOf("z")) to AgentElicitationValidationReason.INVALID_SELECTION,
            "many" to AgentFormValue.TextList(emptyList()) to AgentElicitationValidationReason.BELOW_MINIMUM,
            "many" to AgentFormValue.TextList(listOf("a", "b", "c")) to
                AgentElicitationValidationReason.ABOVE_MAXIMUM,
            "many" to AgentFormValue.TextList(listOf("a", "a")) to
                AgentElicitationValidationReason.DUPLICATE_SELECTION,
        )
        invalidValues.forEach { (entry, reason) ->
            val (name, value) = entry
            val content = mapOf("name" to AgentFormValue.Text("ok"), name to value)
            val validation = elicitation.validate(content)
            assertEquals(reason, validation.issues.single().reason)
            assertEquals(
                validation.isValid,
                elicitation.accepts(AgentElicitationResponse(AgentElicitationAction.ACCEPT, content)),
            )
        }

        val selected = mutableListOf("a")
        val content = mapOf(
            "name" to AgentFormValue.Text("ok"),
            "email" to AgentFormValue.Text("user@example.com"),
            "date" to AgentFormValue.Text("2024-02-29"),
            "timestamp" to AgentFormValue.Text("2026-01-01T12:00:00.123+01:00"),
            "count" to AgentFormValue.Number(2.0),
            "ratio" to AgentFormValue.Number(0.5),
            "enabled" to AgentFormValue.BooleanValue(true),
            "choice" to AgentFormValue.Text("a"),
            "many" to AgentFormValue.TextList(selected),
        )
        val accepted = elicitation.accept(content)
        selected += "b"
        assertTrue(elicitation.accepts(accepted))
        assertEquals(listOf("a"), (accepted.content.getValue("many") as AgentFormValue.TextList).value)
        assertEquals(AgentElicitationResponse(AgentElicitationAction.DECLINE), AgentElicitationResponse.decline())
        assertEquals(AgentElicitationResponse(AgentElicitationAction.CANCEL), AgentElicitationResponse.cancel())
        assertFailsWith<IllegalArgumentException> {
            elicitation.accept(mapOf("name" to AgentFormValue.Text("")))
        }

        val urlOnly = AgentElicitation(
            requestId = "request-url",
            serverName = "server",
            conversationId = ConversationId("thread-1"),
            message = "Authorize",
            url = "https://example.com",
        )
        assertTrue(urlOnly.validate(emptyMap()).isValid)
        assertTrue(urlOnly.accepts(AgentElicitationResponse(AgentElicitationAction.ACCEPT)))
        assertFalse(
            urlOnly.accepts(
                AgentElicitationResponse(
                    AgentElicitationAction.ACCEPT,
                    mapOf("unexpected" to AgentFormValue.Text("value")),
                ),
            ),
        )
    }
}
