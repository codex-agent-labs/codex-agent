package io.github.codex_agent_labs.codexagent.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CodexPublicApiAdoptionTest {
    @Test
    @CoversApi(
        "api-v1:CodexClientInfo#constructor:<init>#sha256:70c21610f4396c3f9bcdfcef68c2b1e2e2968b87e100f4f53b7925dd076f1a0c",
    )
    fun clientIdentityRejectsBlankAndControlCharacters() {
        assertFailsWith<IllegalArgumentException> { CodexClientInfo("", "App", "1") }
        assertFailsWith<IllegalArgumentException> { CodexClientInfo("app", "App\nName", "1") }
        assertFailsWith<IllegalArgumentException> { CodexClientInfo("app", "App", "1\u0000") }
    }

    @Test
    @CoversApi(
        "api-v1:AgentConversationState#constructor:<init>#sha256:0a5cdb8a75f2e34e0caf43336f209e17dcd3ba5565c8e11ff66c4d4974558b05",
        "api-v1:AgentConversationState#property:canCancelTurn#sha256:6370a7dfcc59567be975683bfe6dc5899d773067f419b8d93ab3414942e2d30c",
        "api-v1:AgentConversationState#property:canReload#sha256:28d730b1784c5ca543cea392ab0835fa49d48a6acbb7501011b515ad8730a808",
        "api-v1:AgentConversationState#property:canStartTurn#sha256:16f2352c317aa6ebfa126908ef20b819e8f6f5f7dce7671330a438aa9de17838",
        "api-v1:AgentConversationStatus#enum-entry:CANCELLING_TURN#sha256:eda2fd6fa6eeab75ce558498f48ad9ff652f57820c80a2b2759d0c1239bb4984",
        "api-v1:AgentConversationStatus#enum-entry:CLOSED#sha256:9b78a7a2e8da0c8850912b37397ad18f12d278b073fcdebe5d39b212facf577e",
        "api-v1:AgentConversationStatus#enum-entry:FAILED#sha256:90bda74c53c12246ac217e4bf1a2ccd097b4e4ae2634816c11dc9c9565b49970",
        "api-v1:AgentConversationStatus#enum-entry:NEW#sha256:c25b6f48a3298048f75d164c5dd9b6cd4007894c049ea6d4876925eb5222e046",
        "api-v1:AgentConversationStatus#enum-entry:OPENING#sha256:a4aa316b1cb75beeccb44f40ef30462cc1dd9e1be1f4e36079adf1f9a29e8326",
        "api-v1:AgentConversationStatus#enum-entry:READY#sha256:60cbb992a9fb52f71df7e07b8477603ce27a39b13e1b0d40f7f84c1c8580076f",
        "api-v1:AgentConversationStatus#enum-entry:RELOADING#sha256:3f0bce35466f21426d962567c3835acd24a5bf10fa31dfa588c0a33ce75c8bf5",
        "api-v1:AgentConversationStatus#enum-entry:RUNNING_TURN#sha256:9eb394fd4ba05e0b11ebe9ff3a939994a591a34554199b7a6e9c2183e77d86b5",
        "api-v1:AgentConversationStatus#enum-entry:STARTING_TURN#sha256:6cfb2ff565804122e4f65f3e2c484c782768b2e25e7a1c62b57f6ea2d084a416",
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
        "api-v1:AgentHook#constructor:<init>#sha256:bc7133b8e642e459f23fb12e3431eb937fe22013f759dec3ea906eb8bf73723b",
        "api-v1:AgentHook#property:canTrust#sha256:27eb9c8e059f56faa040869f4a2a6393598aa08963fbc6fe364047e9d7311915",
        "api-v1:AgentHookTrustStatus#enum-entry:MANAGED#sha256:b654d7e38b762be1b67d4a0a5d900f193c9dfad451d2523d6dbeeff3344f1622",
        "api-v1:AgentHookTrustStatus#enum-entry:MODIFIED#sha256:42b43cde24e2bb8e69e5e77533cd0da2b6dc1ce7572e8ce64e20e4527f7fc23c",
        "api-v1:AgentHookTrustStatus#enum-entry:TRUSTED#sha256:845b220bf35e600d9711e45d7780be5e95e657a4f34277b6beea42d678bc0be5",
        "api-v1:AgentHookTrustStatus#enum-entry:UNTRUSTED#sha256:5d40da63cfefb1b4f9a132032603f4132b22eee2f8e22dcb7f5903ac9866d7ee",
        "api-v1:AgentMcpAuthStatus#enum-entry:BEARER_TOKEN#sha256:63e3611e842e4d36ff7828508f3886fa86611b6d52d302a1690913dcacccba88",
        "api-v1:AgentMcpAuthStatus#enum-entry:NOT_LOGGED_IN#sha256:e99adfd2b27893a27a8ec25ee463be8abdc7cf3bc84adb38dfeb68ac266161fd",
        "api-v1:AgentMcpAuthStatus#enum-entry:OAUTH#sha256:853836315a085511e900ba9d3cfa3c047cef4643c2a94b098f980097f1f9ae1c",
        "api-v1:AgentMcpAuthStatus#enum-entry:UNKNOWN#sha256:c94f29a42b3901fc7ff4915c3ccb6f7fed35212b29ab54e04149de8e8d194010",
        "api-v1:AgentMcpAuthStatus#enum-entry:UNSUPPORTED#sha256:0e66ea63382587b427e22476b83250f44ff35ee7c72625d18039e3d33db5bd78",
        "api-v1:AgentMcpServer#constructor:<init>#sha256:ea6c8399a348f247e8550d02ece97b1fc063b1573f148472f974357b013b3cce",
        "api-v1:AgentMcpServer#property:isAuthorized#sha256:470b04e880aaac9064c724b1efc064f51a15e52dcf9feeb2fa379c9728fc9183",
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
        "api-v1:AgentInteractionState#constructor:<init>#sha256:16bfd4583234a43416025115d66106cd793a0a2973924ea283d72873032b61f9",
        "api-v1:AgentInteractionState#function:isResolving#sha256:176fa7c05e0011f4afcc30c94716e4d1096c1c905318cb5114470397b3810978",
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
        "api-v1:AgentElicitation#constructor:<init>#sha256:b86f7d24be50b3bc5439d395760366e6226f8f6c3042eb3528a7614970f10003",
        "api-v1:AgentElicitation#function:accepts#sha256:4165c05860c1f26b2e9f223c1e8e10faca6b6a9a5bda015f4467e976b8cd7f47",
        "api-v1:AgentElicitation#function:accept#sha256:24505de55cad552ca6fa8021cccec79027037b6f356cf3de35914ab063ab2d44",
        "api-v1:AgentElicitation#function:initialValues#sha256:9f21936c2dd3e94293947779f2583b9fc1f7a833d017781f49f6e09bdb15d599",
        "api-v1:AgentElicitation#function:validate#sha256:33f5b475044fdfcf3533f5a9150115de63f15c18ea6f8bd56099efd496e4d26d",
        "api-v1:AgentElicitationAction#enum-entry:ACCEPT#sha256:cb573959c4b58ba10e086addd841221155b710f1fed6e624e1d961ce929fd8db",
        "api-v1:AgentElicitationAction#enum-entry:CANCEL#sha256:d4b66e1a63f88e91cecc84929984692805cf5f60fc9cbd32fed602b7c91dee33",
        "api-v1:AgentElicitationAction#enum-entry:DECLINE#sha256:260fa6821a455131cfc022bebac1d13298aa9d9a8e173ae228f6a0b1b8f445e1",
        "api-v1:AgentElicitationResponse#constructor:<init>#sha256:a7010634f31cd845ea64ee0ddd530161f7492121618228c62eba8b7736e6d865",
        "api-v1:AgentElicitationResponse#property:action#sha256:1b2031521f72890c27f3233f48e7cf8a1e4a04e0fd519779fa0ee1a13d8cd091",
        "api-v1:AgentElicitationResponse#property:content#sha256:d2b4b09969657b85a576f7f4522851043f4630b3f3fcbf7ab561faa6f42dbb25",
        "api-v1:AgentElicitationResponse.Companion#function:cancel#sha256:6a9162b3788c4d1f863774c76bfbba464752ec679c0155aaf140877c5f1fc469",
        "api-v1:AgentElicitationResponse.Companion#function:decline#sha256:b5bebbce67af0027451596f9c1e42b13fe4c1ccd78ac3f8b65f8857f751e3399",
        "api-v1:AgentElicitationValidation#property:isValid#sha256:795b31406f9c936a70bd0767a20054f7721649ca3ff9ed573d1806013e3b4195",
        "api-v1:AgentElicitationValidation#property:issues#sha256:edbcb59235e53720075881cb3ad20ce7023c1fe3cdad57142ede73d921308d93",
        "api-v1:AgentElicitationValidationIssue#property:reason#sha256:941c03fc2e3b5842b434a6f7f526f1d9d903b30cfe4f0d5b3d2a679566f7386b",
        "api-v1:AgentElicitationValidationReason#enum-entry:ABOVE_MAXIMUM#sha256:16ef6ae5f16336a8bea67c724b988df9a224f4e1ffb70e8ecfe843f606605308",
        "api-v1:AgentElicitationValidationReason#enum-entry:BELOW_MINIMUM#sha256:7a9a1ec569a81d2104debab401ee0a59488625a68ef230b6ec70f33cbccae5b0",
        "api-v1:AgentElicitationValidationReason#enum-entry:DUPLICATE_SELECTION#sha256:063af5dea60d003f50a4c7b1eba5ec0f818db5e21e5b028eb80a43cedf1c1e45",
        "api-v1:AgentElicitationValidationReason#enum-entry:INVALID_FORMAT#sha256:e30607165edb61914a0898c1c6e428850d3c53c8c5d0beef88cfdb762a38421c",
        "api-v1:AgentElicitationValidationReason#enum-entry:INVALID_SELECTION#sha256:8ef0b103af106cea97e748d1209b3de305cda674a5fb5a338dbbcf81c6c3f0bb",
        "api-v1:AgentElicitationValidationReason#enum-entry:INVALID_TYPE#sha256:7e7d44440f3e0bba442df29a80e4c3b0054d2e5e95e0dfd64f185062ddd135d1",
        "api-v1:AgentElicitationValidationReason#enum-entry:MISSING_REQUIRED#sha256:e2ff464a42a6a0eae33e268ae3d4e5542120944acc8dc679166c34ef31a8f72b",
        "api-v1:AgentElicitationValidationReason#enum-entry:NON_FINITE_NUMBER#sha256:762dca547f9f32b7d0a30cd047bc9a54384353f0b7a4049df04c98caa849e1be",
        "api-v1:AgentElicitationValidationReason#enum-entry:NON_INTEGER#sha256:471a73df462732e57bbd7614d420647bb330cd4d8468b5ddca803ffd953970fa",
        "api-v1:AgentElicitationValidationReason#enum-entry:UNKNOWN_FIELD#sha256:c64ded5d627a697f07ef1627c66edeab14915f6648a3fd1b3346109c56e3d08e",
        "api-v1:AgentFormField#constructor:<init>#sha256:16548f9c3568321886788527ae507bd796ae4552e8f384d2c22671add51e4f84",
        "api-v1:AgentFormField#property:allowsOther#sha256:acbcb5a606b684c70cc8a0ae0fda32fb581989505157f3c58539b463515d2907",
        "api-v1:AgentFormField#property:defaultValue#sha256:8c5a4f457e5720f77f9e35193c1769665fdc0cebc22fde3dec866e0bb9d840dc",
        "api-v1:AgentFormField#property:format#sha256:12ebef4558c39e8960348f987e7355ca1fca8fcdbfab4f5a7a8cb62dad75f34c",
        "api-v1:AgentFormField#property:isRequired#sha256:3543624f4e02928f4b3c8bc4d28f2014b0464de36631aebf0026e6e67aaf8c2d",
        "api-v1:AgentFormField#property:maximumLength#sha256:61da45738dad83afd9fa01648f6207db80effdb115c258b685f13077ee5bd916",
        "api-v1:AgentFormField#property:maximumSelections#sha256:57bb16ab0789e62ac476cbc49ca29fa0f18fa7bcb15cd318d183815b5b97888d",
        "api-v1:AgentFormField#property:maximum#sha256:f9633d009ceb439d08b0ca87fc09697ce3efb6104356d69584461e975f0aba76",
        "api-v1:AgentFormField#property:minimumLength#sha256:2359be4f7e2b653d66655795a981ecc4fa8e3af7b66b8047a8efca914e2fd6fb",
        "api-v1:AgentFormField#property:minimumSelections#sha256:f5d2632896f59a3f8513ded9b509d538ed3c6c31dc04686edb98f8fbb7438dba",
        "api-v1:AgentFormField#property:minimum#sha256:43f384ccbdf19e9e058b0caf600b7d6a5be872ec372bfde9ab5fab5eb52efd8b",
        "api-v1:AgentFormField#property:name#sha256:4089b2610d698d2336e375928861f927c3f3accab4740222f5585c165e23ae6c",
        "api-v1:AgentFormField#property:options#sha256:fb89092d96f7c40654b98becdc5d26c971fb2c1ee662bd2f4435d6ab8f89261a",
        "api-v1:AgentFormField#property:type#sha256:5556836457c959eda1a695575e3b3581d466de81c42245aa8ac2ea8715fe2ea3",
        "api-v1:AgentFormFieldType#enum-entry:BOOLEAN#sha256:fb8ea9e65bbcbd05fe0f39fb1debb9709e1baa1e6a258d3f476e24df8dd28156",
        "api-v1:AgentFormFieldType#enum-entry:INTEGER#sha256:9900f0a5eae7f33807e2bae94cb72f02bdf67eb5424b02a1bd1448099371eb4b",
        "api-v1:AgentFormFieldType#enum-entry:MULTI_SELECT#sha256:6d82ab5638210781f9e38d91f567bd19c2b4669d8dcad07010188e6f1d11e945",
        "api-v1:AgentFormFieldType#enum-entry:NUMBER#sha256:4bf854ad104678afd344aaecc4d7449084e80a0fbc97d08ca0aecb3fa0471c2a",
        "api-v1:AgentFormFieldType#enum-entry:SINGLE_SELECT#sha256:d561afaf4595e39ef6fc5763db024e8763de7e75eed871167cc6c3521e6a1d56",
        "api-v1:AgentFormFieldType#enum-entry:STRING#sha256:a8bddcaf7bacba0e9fd679e6f851ae3016e40b6ba0aef45dd38798e0aa82423d",
        "api-v1:AgentFormOption#constructor:<init>#sha256:dc27c1dc587d5e0dcd78abcd19062590f9b21191ec93662b6ccd305815003f75",
        "api-v1:AgentFormOption#property:value#sha256:50a7de6055a101c0887c1a74e1c0e18fdf76f9ae1ca87d15c9eac0ac6c3d14b0",
        "api-v1:AgentFormStringFormat#enum-entry:DATE_TIME#sha256:ed4e8fcee76722ef806956e938954a4954e124893a16e90101d20a5a12096112",
        "api-v1:AgentFormStringFormat#enum-entry:DATE#sha256:fab7eae78eaa81e13edfda7ca1afe5e49900b34c102e234d2c973e58320daf35",
        "api-v1:AgentFormStringFormat#enum-entry:EMAIL#sha256:57e0507daa24d443a0f0b0e37b5bf3216ac315c526025507abb6f275eb0b2744",
        "api-v1:AgentFormValue.BooleanValue#constructor:<init>#sha256:5265c04fb81a03abebd1a19094db12a936de6478e7251bce27d890acca04e5da",
        "api-v1:AgentFormValue.BooleanValue#property:value#sha256:334dc879d31834489f7aabc1cf0455476f0e2416fdf703f100f8ab97e91d8503",
        "api-v1:AgentFormValue.Number#constructor:<init>#sha256:0d904371c4a85db517ac3fe307d36e7a63d19afed08ce5ae313f908426e5721f",
        "api-v1:AgentFormValue.Number#property:value#sha256:7cf8272b4242eaef0dd68c62009d2b108c459ef49ca530c59e6c46c91a6712d0",
        "api-v1:AgentFormValue.Text#constructor:<init>#sha256:f8cf274ff98b9e819bca352b3b0ab848eab8926b4a6ea594be0e24c35892b963",
        "api-v1:AgentFormValue.Text#property:value#sha256:968ccfdb61efa8aefa5d9adf9d649420cfbad54ac0c56bc414486f4d5493522c",
        "api-v1:AgentFormValue.TextList#constructor:<init>#sha256:d54b8cf63a07a191780539fb7247c50acd4c8270fd55a35822f07de648f4ac6c",
        "api-v1:AgentFormValue.TextList#property:value#sha256:a3834eb4b5859f1b86de69d8f53714ecae31bb32f1f79f98f6be8091f12af515",
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
