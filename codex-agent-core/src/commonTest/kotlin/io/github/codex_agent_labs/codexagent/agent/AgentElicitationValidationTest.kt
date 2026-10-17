package io.github.codex_agent_labs.codexagent.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AgentElicitationValidationTest {
    @Test
    @CoversApi(
        "api-v1:AgentElicitation#constructor:<init>#sha256:b86f7d24be50b3bc5439d395760366e6226f8f6c3042eb3528a7614970f10003",
        "api-v1:AgentElicitation#function:accepts#sha256:4165c05860c1f26b2e9f223c1e8e10faca6b6a9a5bda015f4467e976b8cd7f47",
        "api-v1:AgentElicitation#property:form#sha256:df55ae80db938ab7f8507b3ba57b3d847f1ff143e1086e8ba80c0e266375c89b",
        "api-v1:AgentElicitation#property:url#sha256:f486144d0838487e4aa26f44394905ae6c566a5ad53fcbd1bd119eb59ea605df",
        "api-v1:AgentElicitationAction#enum-entry:ACCEPT#sha256:cb573959c4b58ba10e086addd841221155b710f1fed6e624e1d961ce929fd8db",
        "api-v1:AgentElicitationAction#enum-entry:CANCEL#sha256:d4b66e1a63f88e91cecc84929984692805cf5f60fc9cbd32fed602b7c91dee33",
        "api-v1:AgentElicitationAction#enum-entry:DECLINE#sha256:260fa6821a455131cfc022bebac1d13298aa9d9a8e173ae228f6a0b1b8f445e1",
        "api-v1:AgentElicitationResponse#constructor:<init>#sha256:a7010634f31cd845ea64ee0ddd530161f7492121618228c62eba8b7736e6d865",
        "api-v1:AgentElicitationResponse#property:action#sha256:1b2031521f72890c27f3233f48e7cf8a1e4a04e0fd519779fa0ee1a13d8cd091",
        "api-v1:AgentFormField#property:isRequired#sha256:3543624f4e02928f4b3c8bc4d28f2014b0464de36631aebf0026e6e67aaf8c2d",
        "api-v1:AgentFormField#property:name#sha256:4089b2610d698d2336e375928861f927c3f3accab4740222f5585c165e23ae6c",
        "api-v1:AgentFormValue.Text#constructor:<init>#sha256:f8cf274ff98b9e819bca352b3b0ab848eab8926b4a6ea594be0e24c35892b963",
        "api-v1:AgentFormValue.Text#property:value#sha256:968ccfdb61efa8aefa5d9adf9d649420cfbad54ac0c56bc414486f4d5493522c",
    )
    fun validatesActionsAndCompleteFormShape() {
        val required = field(
            name = "required",
            type = AgentFormFieldType.STRING,
            isRequired = true,
            defaultValue = AgentFormValue.Text("default"),
        )
        val form = elicitation(form = listOf(required))
        val url = elicitation(url = "https://example.com/authorize")
        val content = mapOf("required" to AgentFormValue.Text("answer"))

        assertTrue(form.accepts(AgentElicitationResponse(AgentElicitationAction.ACCEPT, content)))
        assertFalse(form.accepts(AgentElicitationResponse(AgentElicitationAction.ACCEPT)))
        assertFalse(
            form.accepts(
                AgentElicitationResponse(
                    AgentElicitationAction.ACCEPT,
                    content + ("unknown" to AgentFormValue.Text("value")),
                ),
            ),
        )
        assertTrue(url.accepts(AgentElicitationResponse(AgentElicitationAction.ACCEPT)))
        assertFalse(url.accepts(AgentElicitationResponse(AgentElicitationAction.ACCEPT, content)))

        listOf(AgentElicitationAction.DECLINE, AgentElicitationAction.CANCEL).forEach { action ->
            assertTrue(form.accepts(AgentElicitationResponse(action)))
            assertFalse(form.accepts(AgentElicitationResponse(action, content)))
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentFormField#constructor:<init>#sha256:16548f9c3568321886788527ae507bd796ae4552e8f384d2c22671add51e4f84",
        "api-v1:AgentFormField#function:accepts#sha256:364a5403003f85025375743613b19c44852035ba7f83491c4ec65e1e3501f3ee",
        "api-v1:AgentFormField#property:maximum#sha256:f9633d009ceb439d08b0ca87fc09697ce3efb6104356d69584461e975f0aba76",
        "api-v1:AgentFormField#property:minimum#sha256:43f384ccbdf19e9e058b0caf600b7d6a5be872ec372bfde9ab5fab5eb52efd8b",
        "api-v1:AgentFormField#property:type#sha256:5556836457c959eda1a695575e3b3581d466de81c42245aa8ac2ea8715fe2ea3",
        "api-v1:AgentFormFieldType#enum-entry:BOOLEAN#sha256:fb8ea9e65bbcbd05fe0f39fb1debb9709e1baa1e6a258d3f476e24df8dd28156",
        "api-v1:AgentFormFieldType#enum-entry:INTEGER#sha256:9900f0a5eae7f33807e2bae94cb72f02bdf67eb5424b02a1bd1448099371eb4b",
        "api-v1:AgentFormFieldType#enum-entry:NUMBER#sha256:4bf854ad104678afd344aaecc4d7449084e80a0fbc97d08ca0aecb3fa0471c2a",
        "api-v1:AgentFormFieldType#enum-entry:STRING#sha256:a8bddcaf7bacba0e9fd679e6f851ae3016e40b6ba0aef45dd38798e0aa82423d",
        "api-v1:AgentFormValue.BooleanValue#constructor:<init>#sha256:5265c04fb81a03abebd1a19094db12a936de6478e7251bce27d890acca04e5da",
        "api-v1:AgentFormValue.Number#constructor:<init>#sha256:0d904371c4a85db517ac3fe307d36e7a63d19afed08ce5ae313f908426e5721f",
        "api-v1:AgentFormValue.Number#property:value#sha256:7cf8272b4242eaef0dd68c62009d2b108c459ef49ca530c59e6c46c91a6712d0",
    )
    fun validatesPrimitiveFieldTypesAndNumericBounds() {
        val string = field("string", AgentFormFieldType.STRING, isRequired = true)
        assertAccepted(string, AgentFormValue.Text("value"))
        assertRejected(string, null, AgentFormValue.Text("  "), AgentFormValue.BooleanValue(true))

        val number = field("number", AgentFormFieldType.NUMBER, minimum = 1.0, maximum = 3.0)
        listOf(1.0, 2.5, 3.0).forEach { assertAccepted(number, AgentFormValue.Number(it)) }
        listOf(0.9, 3.1, Double.NaN, Double.POSITIVE_INFINITY).forEach {
            assertRejected(number, AgentFormValue.Number(it))
        }

        val integer = field("integer", AgentFormFieldType.INTEGER, minimum = -2.0, maximum = 2.0)
        listOf(-2.0, 0.0, 2.0).forEach { assertAccepted(integer, AgentFormValue.Number(it)) }
        listOf(-3.0, 1.5, 3.0).forEach { assertRejected(integer, AgentFormValue.Number(it)) }

        val boolean = field("boolean", AgentFormFieldType.BOOLEAN)
        assertAccepted(boolean, AgentFormValue.BooleanValue(false))
        assertRejected(boolean, AgentFormValue.Text("false"))
    }

    @Test
    @CoversApi(
        "api-v1:AgentFormField#property:allowsOther#sha256:acbcb5a606b684c70cc8a0ae0fda32fb581989505157f3c58539b463515d2907",
        "api-v1:AgentFormField#property:options#sha256:fb89092d96f7c40654b98becdc5d26c971fb2c1ee662bd2f4435d6ab8f89261a",
        "api-v1:AgentFormFieldType#enum-entry:MULTI_SELECT#sha256:6d82ab5638210781f9e38d91f567bd19c2b4669d8dcad07010188e6f1d11e945",
        "api-v1:AgentFormFieldType#enum-entry:SINGLE_SELECT#sha256:d561afaf4595e39ef6fc5763db024e8763de7e75eed871167cc6c3521e6a1d56",
        "api-v1:AgentFormOption#constructor:<init>#sha256:dc27c1dc587d5e0dcd78abcd19062590f9b21191ec93662b6ccd305815003f75",
        "api-v1:AgentFormOption#property:value#sha256:50a7de6055a101c0887c1a74e1c0e18fdf76f9ae1ca87d15c9eac0ac6c3d14b0",
        "api-v1:AgentFormValue.TextList#constructor:<init>#sha256:d54b8cf63a07a191780539fb7247c50acd4c8270fd55a35822f07de648f4ac6c",
        "api-v1:AgentFormValue.TextList#property:value#sha256:a3834eb4b5859f1b86de69d8f53714ecae31bb32f1f79f98f6be8091f12af515",
    )
    fun validatesSelectFieldsAndOtherValues() {
        val options = listOf(AgentFormOption("alpha"), AgentFormOption("beta"))
        val single = field("single", AgentFormFieldType.SINGLE_SELECT, options = options)
        assertAccepted(single, AgentFormValue.Text("alpha"))
        assertRejected(single, AgentFormValue.Text("other"))

        val singleWithOther = single.copy(allowsOther = true)
        assertAccepted(singleWithOther, AgentFormValue.Text("other"))
        assertRejected(singleWithOther, AgentFormValue.Text(" "))

        val multi = field(
            "multi",
            AgentFormFieldType.MULTI_SELECT,
            isRequired = true,
            options = options,
        )
        assertAccepted(multi, AgentFormValue.TextList(listOf("alpha", "beta")))
        assertRejected(
            multi,
            AgentFormValue.TextList(emptyList()),
            AgentFormValue.TextList(listOf("alpha", "alpha")),
            AgentFormValue.TextList(listOf("other")),
        )

        val multiWithOther = multi.copy(allowsOther = true)
        assertAccepted(multiWithOther, AgentFormValue.TextList(listOf("alpha", "other")))
        assertRejected(multiWithOther, AgentFormValue.TextList(listOf("alpha", " ")))
    }

    @Test
    @CoversApi(
        "api-v1:AgentElicitationResponse#property:content#sha256:d2b4b09969657b85a576f7f4522851043f4630b3f3fcbf7ab561faa6f42dbb25",
    )
    fun snapshotsCallerOwnedResponseCollections() {
        val selected = mutableListOf("alpha")
        val content = mutableMapOf<String, AgentFormValue>("choices" to AgentFormValue.TextList(selected))

        val snapshot = AgentElicitationResponse(AgentElicitationAction.ACCEPT, content).snapshot()
        selected += "beta"
        content.clear()

        assertEquals(
            mapOf("choices" to AgentFormValue.TextList(listOf("alpha"))),
            snapshot.content,
        )
    }
}

private fun elicitation(
    form: List<AgentFormField>? = null,
    url: String? = null,
): AgentElicitation = AgentElicitation(
    requestId = "request",
    serverName = "server",
    conversationId = ConversationId("conversation"),
    message = "Provide input",
    form = form,
    url = url,
)

private fun field(
    name: String,
    type: AgentFormFieldType,
    isRequired: Boolean = false,
    options: List<AgentFormOption> = emptyList(),
    defaultValue: AgentFormValue? = null,
    minimum: Double? = null,
    maximum: Double? = null,
): AgentFormField = AgentFormField(
    name = name,
    title = name,
    type = type,
    isRequired = isRequired,
    options = options,
    defaultValue = defaultValue,
    minimum = minimum,
    maximum = maximum,
)

private fun assertAccepted(field: AgentFormField, vararg values: AgentFormValue?) {
    values.forEach { value -> assertTrue(field.accepts(value), "$field should accept $value") }
}

private fun assertRejected(field: AgentFormField, vararg values: AgentFormValue?) {
    values.forEach { value -> assertFalse(field.accepts(value), "$field should reject $value") }
}
