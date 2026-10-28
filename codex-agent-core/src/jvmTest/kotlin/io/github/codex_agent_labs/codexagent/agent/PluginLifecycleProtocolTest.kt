package io.github.codex_agent_labs.codexagent.agent

import io.github.codex_agent_labs.codexagent.appserver.protocol.generated.*
import io.github.codex_agent_labs.codexagent.agent.*
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*

class PluginLifecycleProtocolTest : SkillsPluginsProtocolTestBase() {
    @CoversApi(
        "api-v1:AgentInvocation#property:key#sha256:329debe23424891c03b5e1705db2e83c34704ba44e4b78707e5df9cbaf031b05",
        "api-v1:AgentInvocation#property:name#sha256:93a9155e710959e03247cf1e3eb08d511b24bc3ab11d33f29928d2265fd81eee",
        "api-v1:AgentInvocation.Plugin#constructor:<init>#sha256:2c51d39a0f6d4bd4e56af5d7a39927f608ad6655e2586c78ffdf37e97dc730fc",
        "api-v1:AgentInvocation.Plugin#property:key#sha256:5aa4ba1448f61432ec190424fc8412dea85ef3d40a0c1083b455870dababddc7",
        "api-v1:AgentInvocation.Plugin#property:name#sha256:e912e6dbf23a3bfe27a28c6c88b3b99f643130b9cca842e6ab41f46989f4f72f",
        "api-v1:AgentInvocation.Plugin#property:uri#sha256:0616140eab0aa6f3f003f76274e33ee713feaf2bc35f666ed4739ef13eb4d33e",
        "api-v1:AgentInvocation.Skill#constructor:<init>#sha256:1ce70d208f24e728ffbfbb72b505947d1e1f19190f918338ba11f4748efe2af5",
        "api-v1:AgentInvocation.Skill#property:key#sha256:011242f4a6b79bca1f4a5842f0fe1607fe5fb3e13f7752f0049bf881367e0cf5",
        "api-v1:AgentInvocation.Skill#property:name#sha256:926be88f7745678d19dbaadd311aed1091a2a771a7bd8ca9e94365f60635ef33",
        "api-v1:AgentInvocation.Skill#property:path#sha256:35d1ce3d1d081402d0cb3eebb581584a54685d4b87d276b7f866ed307ee459b4",
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
        "api-v1:AgentElicitation#property:form#sha256:df55ae80db938ab7f8507b3ba57b3d847f1ff143e1086e8ba80c0e266375c89b",
        "api-v1:AgentFormField#property:format#sha256:12ebef4558c39e8960348f987e7355ca1fca8fcdbfab4f5a7a8cb62dad75f34c",
        "api-v1:AgentFormField#property:isRequired#sha256:3543624f4e02928f4b3c8bc4d28f2014b0464de36631aebf0026e6e67aaf8c2d",
        "api-v1:AgentFormField#property:maximumLength#sha256:61da45738dad83afd9fa01648f6207db80effdb115c258b685f13077ee5bd916",
        "api-v1:AgentFormField#property:maximumSelections#sha256:57bb16ab0789e62ac476cbc49ca29fa0f18fa7bcb15cd318d183815b5b97888d",
        "api-v1:AgentFormField#property:minimumLength#sha256:2359be4f7e2b653d66655795a981ecc4fa8e3af7b66b8047a8efca914e2fd6fb",
        "api-v1:AgentFormField#property:minimumSelections#sha256:f5d2632896f59a3f8513ded9b509d538ed3c6c31dc04686edb98f8fbb7438dba",
        "api-v1:AgentFormField#property:type#sha256:5556836457c959eda1a695575e3b3581d466de81c42245aa8ac2ea8715fe2ea3",
        "api-v1:AgentFormFieldType#enum-entry:BOOLEAN#sha256:fb8ea9e65bbcbd05fe0f39fb1debb9709e1baa1e6a258d3f476e24df8dd28156",
        "api-v1:AgentFormFieldType#enum-entry:MULTI_SELECT#sha256:6d82ab5638210781f9e38d91f567bd19c2b4669d8dcad07010188e6f1d11e945",
        "api-v1:AgentFormFieldType#enum-entry:SINGLE_SELECT#sha256:d561afaf4595e39ef6fc5763db024e8763de7e75eed871167cc6c3521e6a1d56",
        "api-v1:AgentFormFieldType#enum-entry:STRING#sha256:a8bddcaf7bacba0e9fd679e6f851ae3016e40b6ba0aef45dd38798e0aa82423d",
        "api-v1:AgentFormStringFormat#enum-entry:EMAIL#sha256:57e0507daa24d443a0f0b0e37b5bf3216ac315c526025507abb6f275eb0b2744",
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
        "api-v1:AgentFormField#property:allowsOther#sha256:acbcb5a606b684c70cc8a0ae0fda32fb581989505157f3c58539b463515d2907",
        "api-v1:AgentFormField#property:options#sha256:fb89092d96f7c40654b98becdc5d26c971fb2c1ee662bd2f4435d6ab8f89261a",
        "api-v1:AgentFormOption#property:description#sha256:563fe3a76ad8fc6046ccb6d3acf3ce891ddde818f6241e51cee180eba623187b",
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
