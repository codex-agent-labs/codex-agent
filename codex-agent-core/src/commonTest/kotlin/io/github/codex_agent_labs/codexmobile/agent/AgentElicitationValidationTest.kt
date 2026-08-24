package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AgentElicitationValidationTest {
    @Test
    @CoversApi(
        "api-v1:AgentElicitation#constructor:<init>#sha256:cf9662bd2ac45ca550019b2e010fc9f2759ca40a83b04c8bdd0fa077b8dd1273",
        "api-v1:AgentElicitation#function:accepts#sha256:8ba4c2f5f4d79b298b491b66e2f950c954cab92f9606e2d2d66c8080500259d6",
        "api-v1:AgentElicitation#property:form#sha256:55c5975d6def5c6032d2e64571b8e289e3bbf2872c1f1828ae47201a10eefbb4",
        "api-v1:AgentElicitation#property:url#sha256:fab075c72476bc857979187a2f9e5e06d1bfc5a1f1fb9d06498c10ce7f7733d7",
        "api-v1:AgentElicitationAction#enum-entry:ACCEPT#sha256:c481b65c165c21a081bfc1ed4f2a6c58e0118dd451e3869b8a80b0a2cf2dcc11",
        "api-v1:AgentElicitationAction#enum-entry:CANCEL#sha256:2247d8fb7ccecf2021557b03d85a9e35917d69767a970690e9e87c0f77dc79cd",
        "api-v1:AgentElicitationAction#enum-entry:DECLINE#sha256:b3fb0b76797e7471af7e95d7f7357fc80c2fa04ceef2e2b8ee368e58bf55c525",
        "api-v1:AgentElicitationResponse#constructor:<init>#sha256:d29f5881ad792d369bd644bf64a81af6e7f10d9e898fa97fc6da5d79953a91ea",
        "api-v1:AgentElicitationResponse#property:action#sha256:05992eb60ebeae70d41d0f1152d1af78aa270d826104f73edc1c564db58f1660",
        "api-v1:AgentFormField#property:isRequired#sha256:0b61d59c19120666031a45a49a98cac21964653c1e5c2218e35edd87a704a8b8",
        "api-v1:AgentFormField#property:name#sha256:80cebf494511792d2bcebc4fdc08df319a2048702999af3a4635130d47cbb645",
        "api-v1:AgentFormValue.Text#constructor:<init>#sha256:5b5a2473564a3c8e8550758f331f57a7f824b314b779e1b9b1aa0a58b4e499fd",
        "api-v1:AgentFormValue.Text#property:value#sha256:54fc56f883e53106a8daf40efabde4c04e226b1ef0d9d8598ae9f8f31441369c",
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
        "api-v1:AgentFormField#constructor:<init>#sha256:0b99885f2600d03c98585f40760b688318ae6c876c41b68fe1735d250c4b20c2",
        "api-v1:AgentFormField#function:accepts#sha256:caa7da915f82aa67dd8d39686d808867cd0c5f9543d35a4515442ec58d90940f",
        "api-v1:AgentFormField#property:maximum#sha256:25477c28e30e72f993eba973ce5a3882866f33b263760fc4e7b5168bc3ccd62a",
        "api-v1:AgentFormField#property:minimum#sha256:73bd8d8f4e59dd327b6cf3c38e908520492dd450db78d311fdc6ca7dfb8f5f4d",
        "api-v1:AgentFormField#property:type#sha256:5df1e80ecf023dac2ee69b7777db3ea25b9fe666fb15c003b0a3b3c4e3461238",
        "api-v1:AgentFormFieldType#enum-entry:BOOLEAN#sha256:65c0765a32419ffd6a5d3bdcc580be3b146268619c20c7108348d40ab5ba9505",
        "api-v1:AgentFormFieldType#enum-entry:INTEGER#sha256:4c627864a11e5d38c2bcc6982c29a5d2d5d7493b2dc3c1d515a01696fad90850",
        "api-v1:AgentFormFieldType#enum-entry:NUMBER#sha256:bd931ffcde038dc0205940be48e10c2e0a587255f423f8724fa6e2bb09852f39",
        "api-v1:AgentFormFieldType#enum-entry:STRING#sha256:1ee3d7c1f1f81356a4ad51152ec3d66692142ad597c4955c1abdfdadfdd7c4dc",
        "api-v1:AgentFormValue.BooleanValue#constructor:<init>#sha256:ba4dbbf961dca60138a90b01cc14645fa9edca4fc46b68832dc5dbfc80ffb8e7",
        "api-v1:AgentFormValue.Number#constructor:<init>#sha256:23f8fdcbf37481f215f67d1ea4463901be5a0960d7da812ba96b7fe7b59974dc",
        "api-v1:AgentFormValue.Number#property:value#sha256:b28d23fab557d74452f20536918401859e2d1ef47636b2bb86b3f7da7d3a4503",
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
        "api-v1:AgentFormField#property:allowsOther#sha256:1534af7ae95a1141bf1007870e2e9101d23cdd6e9f696858a10bb8235db3c0f8",
        "api-v1:AgentFormField#property:options#sha256:8ed46849b09eabcf6d84b04fde4b7097d47a2676953656e0ee82811d31a031ec",
        "api-v1:AgentFormFieldType#enum-entry:MULTI_SELECT#sha256:557054dd108843dacf6c85a51354e44779de04f994c63521746e3299ca5a2952",
        "api-v1:AgentFormFieldType#enum-entry:SINGLE_SELECT#sha256:fc2963015442b1745254904f02fd5729a22d0f6f691e52dc14218f719c986e55",
        "api-v1:AgentFormOption#constructor:<init>#sha256:2c8c2dd1747e26e034dff4b9db6bed87caab59d76d472e9fbfd6e488212c42a3",
        "api-v1:AgentFormOption#property:value#sha256:2359d75888e8fbbb52e343e42b18030421cfc4f960d7ea9acd83e9de613cedbb",
        "api-v1:AgentFormValue.TextList#constructor:<init>#sha256:881e244857bc4e1ce48b82bea49f689ce704308cdf95d9dee9df0d622b402110",
        "api-v1:AgentFormValue.TextList#property:value#sha256:e35325f387fa78b8cf134b1faeb4e227d3781ee31b80b18931d0c45540181fcf",
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
        "api-v1:AgentElicitationResponse#property:content#sha256:f9210ef8b5b183d9b0bf771df60d1c104257e0d1c4a3acd6d914c06213e8b078",
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
