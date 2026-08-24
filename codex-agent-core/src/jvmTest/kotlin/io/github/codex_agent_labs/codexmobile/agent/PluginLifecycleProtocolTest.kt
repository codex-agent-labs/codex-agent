package io.github.codex_agent_labs.codexmobile.agent

import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.*
import io.github.codex_agent_labs.codexmobile.agent.*
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*

class PluginLifecycleProtocolTest : SkillsPluginsProtocolTestBase() {
    @CoversApi(
        "api-v1:AgentInvocation#property:key#sha256:95a13afd0e17169c6c7c61e6d42bf69b1b117d21ff0bbb6905867d6bf15d32aa",
        "api-v1:AgentInvocation#property:name#sha256:75c30faa3ef13b680d293101364bdfdce8747e9536744983337b10d1ff304f5e",
        "api-v1:AgentInvocation.Plugin#constructor:<init>#sha256:412c7e9beb326730d1f60d02504862c51ba7022f3e3db05936b7016cbd74ad5c",
        "api-v1:AgentInvocation.Plugin#property:key#sha256:896cc1b2c42d2060cdaa50537c3a2115863cb27341607df89820033b5306cc90",
        "api-v1:AgentInvocation.Plugin#property:name#sha256:50d95f609e1c7b9634955a41797520a6fe95320a64dafc6e6fc58e9198e64ae6",
        "api-v1:AgentInvocation.Plugin#property:uri#sha256:991280af8c427be99c9ac6d23e1f79b8bdba62b2c3735b134a5d6e043aa5987b",
        "api-v1:AgentInvocation.Skill#constructor:<init>#sha256:c50d8707f855ef964ec2e75034505b082d76d9b9a44801b37cc1646de6646306",
        "api-v1:AgentInvocation.Skill#property:key#sha256:542d856580844e6e402ea719f25b18e82d28d05629b7053106e65e755e7b9775",
        "api-v1:AgentInvocation.Skill#property:name#sha256:a9b5be5d2a41b6aa9152b749b6290df55d53e332ab6cbc9a2e2182664bd32753",
        "api-v1:AgentInvocation.Skill#property:path#sha256:0e701b0a08a8d13edd5a9b2b7664dc106a1f9edd97d4391498206d04e163c994",
    )
    @Test
    fun encodesOrderedDeduplicatedSkillAndPluginInvocations() {
        val skill = AgentInvocation.Skill("review", "/skills/review/SKILL.md")
        val plugin = AgentInvocation.Plugin("drive", "plugin://drive@openai-curated")
        val input = turnInput(
            AgentTurnRequest(
                prompt = "Check this",
                invocations = listOf(skill, plugin, skill),
            ),
        )

        assertEquals("\$review\n@drive\n\nCheck this", assertIs<UserInputTextUserInput>(input[0]).text)
        assertEquals("/skills/review/SKILL.md", assertIs<UserInputSkillUserInput>(input[1]).path)
        assertEquals("plugin://drive@openai-curated", assertIs<UserInputMentionUserInput>(input[2]).path)
    }

    @CoversApi(
        "api-v1:AgentElicitation#property:form#sha256:55c5975d6def5c6032d2e64571b8e289e3bbf2872c1f1828ae47201a10eefbb4",
        "api-v1:AgentFormField#property:format#sha256:da32b5d1c20e2690e0e3cfd1041b50e773b533173f321f11401e23af1f1aea04",
        "api-v1:AgentFormField#property:isRequired#sha256:0b61d59c19120666031a45a49a98cac21964653c1e5c2218e35edd87a704a8b8",
        "api-v1:AgentFormField#property:maximumLength#sha256:04a38b40b996fc3ffadc4edd8a989f9217b6e23679261743bee8ae4cc474f979",
        "api-v1:AgentFormField#property:maximumSelections#sha256:63928cb03a66b2e47ac1fcab509f6fd0723fd20c370fe8c7af1516c2b55affeb",
        "api-v1:AgentFormField#property:minimumLength#sha256:9db5a3b3e8bf01c9443e297e0364974ed1dbfee889d17065663894e935b9fc82",
        "api-v1:AgentFormField#property:minimumSelections#sha256:97122b459fe73fe4c05abbf62e16a26b47cf130752a79c03c605696169e5c145",
        "api-v1:AgentFormField#property:type#sha256:5df1e80ecf023dac2ee69b7777db3ea25b9fe666fb15c003b0a3b3c4e3461238",
        "api-v1:AgentFormFieldType#enum-entry:BOOLEAN#sha256:65c0765a32419ffd6a5d3bdcc580be3b146268619c20c7108348d40ab5ba9505",
        "api-v1:AgentFormFieldType#enum-entry:MULTI_SELECT#sha256:557054dd108843dacf6c85a51354e44779de04f994c63521746e3299ca5a2952",
        "api-v1:AgentFormFieldType#enum-entry:SINGLE_SELECT#sha256:fc2963015442b1745254904f02fd5729a22d0f6f691e52dc14218f719c986e55",
        "api-v1:AgentFormFieldType#enum-entry:STRING#sha256:1ee3d7c1f1f81356a4ad51152ec3d66692142ad597c4955c1abdfdadfdd7c4dc",
        "api-v1:AgentFormStringFormat#enum-entry:EMAIL#sha256:9524032512d558a58da9cd71135c5b07676eb03f7590acb270f463e0ffec40ec",
    )
    @Test
    fun decodesSupportedElicitationFormsAndRejectsUnsafeUrls() {
        val elicitation = parseElicitation(
            "7",
            Json.decodeFromJsonElement(McpServerElicitationRequestParams.serializer(), buildJsonObject {
                put("serverName", "drive")
                put("threadId", "thread-1")
                put("message", "Choose")
                put("mode", "form")
                putJsonObject("requestedSchema") {
                    put("type", "object")
                    putJsonArray("required") { add(JsonPrimitive("folder")) }
                    putJsonObject("properties") {
                        putJsonObject("folder") {
                            put("type", "string")
                            put("title", "Folder")
                            put("minLength", 2)
                            put("maxLength", 10)
                        }
                        putJsonObject("email") {
                            put("type", "string")
                            put("format", "email")
                        }
                        putJsonObject("format") {
                            put("type", "string")
                            putJsonArray("enum") { add(JsonPrimitive("pdf")); add(JsonPrimitive("docx")) }
                        }
                        putJsonObject("notify") { put("type", "boolean") }
                        putJsonObject("tags") {
                            put("type", "array")
                            put("minItems", 1)
                            put("maxItems", 2)
                            putJsonObject("items") {
                                put("type", "string")
                                putJsonArray("enum") { add("a"); add("b") }
                            }
                        }
                    }
                }
            }),
        )

        val form = requireNotNull(elicitation.form)
        assertEquals(listOf(
            AgentFormFieldType.STRING,
            AgentFormFieldType.STRING,
            AgentFormFieldType.SINGLE_SELECT,
            AgentFormFieldType.BOOLEAN,
            AgentFormFieldType.MULTI_SELECT,
        ),
            form.map { it.type })
        assertTrue(form.first().isRequired)
        assertEquals(2L, form.first().minimumLength)
        assertEquals(10L, form.first().maximumLength)
        assertEquals(AgentFormStringFormat.EMAIL, form[1].format)
        assertEquals(1L, form.last().minimumSelections)
        assertEquals(2L, form.last().maximumSelections)
        assertFailsWith<IllegalArgumentException> { requireSafeAuthUrl("http://192.168.1.2/login") }
        assertEquals("http://127.0.0.1:9876/callback", requireSafeAuthUrl("http://127.0.0.1:9876/callback"))
    }

    @CoversApi(
        "api-v1:AgentFormField#property:allowsOther#sha256:1534af7ae95a1141bf1007870e2e9101d23cdd6e9f696858a10bb8235db3c0f8",
        "api-v1:AgentFormField#property:options#sha256:8ed46849b09eabcf6d84b04fde4b7097d47a2676953656e0ee82811d31a031ec",
        "api-v1:AgentFormOption#property:description#sha256:0c088fdc2ba2b4b146e950a08eb5a8735e44dc336f5811886b2be8ac05e9dacd",
    )
    @Test
    fun mapsPlanQuestionsToSelectableMobileFormFields() {
        val elicitation = parseUserInputRequest(
            "9",
            ToolRequestUserInputParams(
                isBlocking = true,
                itemId = "item-1",
                threadId = "thread-1",
                turnId = "turn-1",
                questions = listOf(
                    ToolRequestUserInputQuestion(
                        header = "Dates",
                        id = "dates",
                        question = "Are your dates flexible?",
                        isOther = true,
                        options = listOf(ToolRequestUserInputOption("Any week works", "Flexible")),
                    ),
                ),
            ),
        )

        val field = elicitation.form!!.single()
        assertEquals(AgentFormFieldType.SINGLE_SELECT, field.type)
        assertEquals("Any week works", field.options.single().description)
        assertTrue(field.allowsOther)
    }

}
