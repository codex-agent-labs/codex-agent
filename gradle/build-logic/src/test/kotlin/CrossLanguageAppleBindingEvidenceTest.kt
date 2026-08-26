import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.tasks.CacheableTask
import org.gradle.testfixtures.ProjectBuilder

class CrossLanguageAppleBindingEvidenceTest {
    @Test
    fun `observes 499 independent claims and 57 explicit gaps per Apple language`() {
        val fixture = fixture()
        val report = fixture.derive()

        assertEquals(1, report.releaseInt("schemaVersion"))
        assertEquals(APPLE_BINDING_EVIDENCE_PROTOCOL, report.releaseString("protocol"))
        assertEquals("observed", report.releaseString("result"))
        assertFalse("receipt" in report)
        assertFalse("parity" in report)
        val languages = report.releaseArray("languages").map { it as JsonObject }
        assertEquals(listOf("objective-c", "swift"), languages.map { it.releaseString("language") })
        languages.forEach { language ->
            assertEquals(613, language.releaseArray("publicSymbols").size)
            assertEquals(499, language.releaseArray("referencedSymbols").size)
            assertEquals(499, language.releaseArray("claims").size)
            assertTrue(language.releaseArray("exclusions").isEmpty())
            assertEquals(57, language.releaseArray("missingCapabilityKeys").size)
            assertEquals(
                fixture.capabilities,
                language.releaseArray("claims").map { (it as JsonObject).releaseString("canonicalKey") },
            )
            val behaviorTest = if (language.releaseString("language") == "swift") {
                SWIFT_FAILURE_TEST
            } else {
                OBJECTIVE_C_FAILURE_TEST
            }
            assertTrue(language.releaseArray("claims").all {
                val claim = it as JsonObject
                claim.releaseString("behaviorTest") == behaviorTest &&
                    claim.releaseString("publicSymbol") == claim.releaseString("compilerReference")
            })
        }
    }

    @Test
    fun `fails closed on canonical surface reference claim artifact target and XCTest drift`() {
        val fixture = fixture()
        val compiler = fixture.compiler
        val surface = compiler.releaseObject("surface")
        val swift = surface.releaseArray("swift")
        fun surfaceIndex(language: String, precise: String): Int =
            surface.releaseArray(language).indexOfFirst {
                (it as JsonObject).releaseString("precise") == precise
            }.also { check(it >= 0) { "Missing fixture symbol: $precise" } }
        val swiftCodeIndex = surfaceIndex("swift", CODE_USR)
        val changedSwift = JsonArray(swift.mapIndexed { index, value ->
            if (index == swiftCodeIndex) {
                JsonObject((value as JsonObject) + ("accessLevel" to JsonPrimitive("public")))
            } else {
                value
            }
        })
        val surfaceDrift = compiler.withObject("surface", JsonObject(surface + mapOf(
            "swift" to changedSwift,
            "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changedSwift)),
        )))
        val signatureDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", CONSTRUCTOR),
            "declaration", JsonPrimitive("init(code: String, message: String)"),
        )
        val typeDrift = compiler.surfaceDrift(
            "swift", swiftCodeIndex, "typeIdentifiers", strings(listOf("s:Si")),
        )
        val readonlyDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", CODE_USR),
            "declaration", JsonPrimitive("@property (readwrite) NSString * code;"),
        )
        val selectorDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", CONSTRUCTOR),
            "title", JsonPrimitive("initWithMessage:code:isRecoverable:"),
        )
        val ordinaryEnumDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", D065_ENUM_USR), "title", JsonPrimitive("removed"),
        )
        val ordinaryConstructorDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", D065_CONSTRUCTOR_USR),
            "parameters", buildJsonArray {},
        )
        val ordinaryPropertyDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", D065_PROPERTY_USR),
            "typeIdentifiers", strings(listOf("s:Si")),
        )
        val authorizationFactoryDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", AUTHORIZATION_CHAT_GPT_USR),
            "declaration", JsonPrimitive("func chatGpt(value: String?) -> CodexAuthorizationUrl"),
        )
        val authorizationPurposeDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", AUTHORIZATION_PURPOSE_USR),
            "typeIdentifiers", strings(listOf("c:objc(cs)NSString")),
        )
        val d077ConstructorUsr = appleCompilerFixtureD077Capabilities.single {
            "/AgentMcpServer.<init>|" in it.canonicalKey
        }.usr
        val d077ConfigurationUsr = appleCompilerFixtureD077Capabilities.single {
            "/AgentMcpServer.configuration|" in it.canonicalKey
        }.usr
        val d077ConstructorDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", d077ConstructorUsr),
            "parameters", buildJsonArray {},
        )
        val d077NullablePropertyDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d077ConfigurationUsr),
            "declaration", JsonPrimitive("var configuration: AgentMcpServerConfiguration { get }"),
        )
        val d078ContentUsr = appleCompilerFixtureD078Capabilities.single {
            "/AgentElicitationResponse.content|" in it.canonicalKey
        }.usr
        val d078ContentIdentifierDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d078ContentUsr), "typeIdentifiers",
            strings(listOf("c:objc(pl)CodexAgentAgentFormValue", "s:SS")),
        )
        val d079ConstructorUsr = appleCompilerFixtureD079Capabilities.single {
            "/AgentMessage.<init>|" in it.canonicalKey
        }.usr
        val d079CapabilitiesUsr = appleCompilerFixtureD079Capabilities.single {
            "/AgentMessage.capabilities|" in it.canonicalKey
        }.usr
        val d079SetIdentifierDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d079CapabilitiesUsr), "typeIdentifiers",
            strings(listOf("c:objc(cs)CodexAgentAgentCapability", "s:Sh")),
        )
        val d079ConstructorSurfaceDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", d079ConstructorUsr),
            "parameters", buildJsonArray {},
        )
        val d080ConstructorUsr = appleCompilerFixtureD080Capabilities.single {
            "/AgentAuthenticationState.<init>|" in it.canonicalKey
        }.usr
        val d080MethodUsr = appleCompilerFixtureD080Capabilities.single {
            "/AgentInteractionState.pendingFor|" in it.canonicalKey
        }.usr
        val d080SetPropertyUsr = appleCompilerFixtureD080Capabilities.single {
            "/AgentInteractionState.resolvingRequestIds|" in it.canonicalKey
        }.usr
        val d080ConstructorSurfaceDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", d080ConstructorUsr),
            "parameters", buildJsonArray {},
        )
        val d080MethodSurfaceDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d080MethodUsr),
            "declaration", JsonPrimitive(
                "func pendingFor(conversationId: ConversationId) -> [String]",
            ),
        )
        val d080SetIdentifierDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d080SetPropertyUsr), "typeIdentifiers",
            strings(listOf("s:SS", "s:Sh")),
        )
        val d081SharedUsr = appleCompilerFixtureD081Capabilities.single {
            "/AgentHookHandler.Agent|" in it.canonicalKey
        }.usr
        val d081SharedSurfaceDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d081SharedUsr),
            "declaration", JsonPrimitive("class var shared: AgentHookHandlerPrompt { get }"),
        )
        val d082ValidateUsr = appleCompilerFixtureD082Capabilities.single {
            "/AgentElicitation.validate|" in it.canonicalKey
        }.usr
        val d082CancelUsr = appleCompilerFixtureD082Capabilities.single {
            "/AgentElicitationResponse.Companion.cancel|" in it.canonicalKey
        }.usr
        val d082SurfaceDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d082ValidateUsr),
            "declaration", JsonPrimitive(
                "func validate(content: [String : any AgentFormValue]) -> Bool",
            ),
        )
        val d083ConversationIdUsr = appleCompilerFixtureD083Capabilities.single {
            "/AgentPendingInteraction.conversationId|" in it.canonicalKey
        }.usr
        val d083SurfaceDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d083ConversationIdUsr),
            "typeIdentifiers", strings(listOf("s:SS")),
        )
        val d084HostStartUsr = appleCompilerFixtureD084Capabilities.single {
            "/CodexHost.start|" in it.canonicalKey
        }.usr
        val d084FailedWorkspaceUsr = appleCompilerFixtureD084Capabilities.single {
            "/CodexHostState.Failed.workspace|" in it.canonicalKey
        }.usr
        val d084HostConstructorUsr = appleCompilerFixtureD084Capabilities.single {
            "/CodexHost|kind=constructor|" in it.canonicalKey
        }.usr
        val d084FailedConstructorUsr = appleCompilerFixtureD084Capabilities.single {
            "/CodexHostState.Failed|kind=constructor|" in it.canonicalKey
        }.usr
        val d084AsyncSurfaceDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d084HostStartUsr),
            "declaration", JsonPrimitive("func start() async"),
        )
        val d084NullableSurfaceDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", d084FailedWorkspaceUsr),
            "declaration", JsonPrimitive(
                "@property (readonly) CodexAgentCodexWorkspace * _Nonnull workspace;",
            ),
        )
        val d085WorkspaceUsr = appleCompilerFixtureD085Capabilities.single {
            "/CodexAgent.workspace|" in it.canonicalKey
        }.usr
        val d085SkillsAvailabilityUsr = appleCompilerFixtureD085Capabilities.single {
            "/CodexSkills.isAvailable|" in it.canonicalKey
        }.usr
        val d085WorkspaceSurfaceDrift = compiler.surfaceDrift(
            "swift", surfaceIndex("swift", d085WorkspaceUsr),
            "typeIdentifiers", strings(listOf("c:objc(cs)CodexAgentCodexSkills")),
        )
        val d085AvailabilitySurfaceDrift = compiler.surfaceDrift(
            "objectiveC", surfaceIndex("objectiveC", d085SkillsAvailabilityUsr),
            "declaration", JsonPrimitive("@property (readonly) NSInteger isAvailable;"),
        )
        val missingSurface = compiler.withObject("surface", run {
            val reduced = JsonArray(swift.dropLast(1))
            JsonObject(surface + mapOf(
                "swift" to reduced,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(reduced)),
            ))
        })
        val duplicateSurface = compiler.withObject("surface", run {
            val duplicated = JsonArray(swift + swift.last())
            JsonObject(surface + mapOf(
                "swift" to duplicated,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(duplicated)),
            ))
        })
        val references = compiler.releaseObject("references")
        val missingReference = JsonArray(references.releaseArray("objectiveC").dropLast(1))
        val referenceDrift = compiler.withObject("references", JsonObject(references + mapOf(
            "objectiveC" to missingReference,
            "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(missingReference)),
        )))
        val swiftReferenceTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == ACCEPT_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSo31CodexAgentAgentApprovalDecisionCD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val collaborationReferenceTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == PLAN_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSo010CodexAgentB16ApprovalDecisionCD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val messageRoleReferenceTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == ASSISTANT_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive(COLLABORATION_SWIFT_TYPE)))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val installationScopeReferenceTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == INSTALLATION_WORKSPACE_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive(MESSAGE_ROLE_SWIFT_TYPE)))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val mcpEnvironmentSourceReferenceTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == MCP_ENVIRONMENT_REMOTE_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive(INSTALLATION_SCOPE_SWIFT_TYPE)))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val mcpEnvironmentSourceReceiverDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == MCP_ENVIRONMENT_LOCAL_USR) {
                    JsonObject(reference + ("receiverType" to JsonPrimitive("CodexAgentAgentInstallationScope")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val conversationIdConstructorTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == CONVERSATION_ID_CONSTRUCTOR_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSSD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val conversationIdReceiverDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == CONVERSATION_ID_VALUE_USR) {
                    JsonObject(reference + ("receiverType" to JsonPrimitive("CodexAgentCodexFailure *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val qualifierDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == ACCEPT_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("CodexAgentAgentApprovalDecision *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val authorizationSwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == AUTHORIZATION_CHAT_GPT_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSSD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val authorizationObjectiveCReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == AUTHORIZATION_EXTERNAL_USR) {
                    JsonObject(reference +
                        ("receiverType" to JsonPrimitive("CodexAgentCodexAuthorizationUrl *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d077SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d077ConstructorUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSSD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d077ObjectiveCConstructorDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d077ConstructorUsr) {
                    JsonObject(reference + ("argumentTypes" to strings(listOf("NSString *"))))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d077ObjectiveCReceiverDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d077ConfigurationUsr) {
                    JsonObject(reference +
                        ("receiverType" to JsonPrimitive("CodexAgentAgentMcpServerConfiguration *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d078SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d078ContentUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSSD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d078ObjectiveCReceiverDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d078ContentUsr) {
                    JsonObject(reference +
                        ("receiverType" to JsonPrimitive("CodexAgentAgentElicitationResponseCompanion *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d079SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d079CapabilitiesUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSSD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d079ObjectiveCConstructorDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d079ConstructorUsr) {
                    JsonObject(reference + ("argumentTypes" to strings(listOf("NSString *"))))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d080SwiftMethodReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d080MethodUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSbD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d080ObjectiveCMethodReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d080MethodUsr) {
                    JsonObject(reference + ("argumentTypes" to strings(listOf("NSString *"))))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d081SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d081SharedUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive(
                        "\$sSo010CodexAgentB17HookHandlerPromptCD",
                    )))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d081ObjectiveCReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d081SharedUsr) {
                    JsonObject(reference + ("receiverType" to JsonPrimitive(
                        "CodexAgentAgentHookHandlerPrompt",
                    )))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d082SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d082ValidateUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSbD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d082ObjectiveCReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d082CancelUsr) {
                    JsonObject(reference + ("receiverType" to JsonPrimitive(
                        "CodexAgentAgentElicitation *",
                    )))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d083SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d083ConversationIdUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSSD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d083ObjectiveCReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d083ConversationIdUsr) {
                    JsonObject(reference + ("receiverType" to JsonPrimitive(
                        "CodexAgentAgentPendingApproval *",
                    )))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d084SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d084HostStartUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$syyycSo010CodexAgentA4HostCcD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d084ObjectiveCReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d084HostStartUsr) {
                    JsonObject(reference + ("argumentTypes" to strings(listOf("void *"))))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d084ObjectiveCConstructorReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                when (reference.releaseString("precise")) {
                    d084HostConstructorUsr -> JsonObject(reference + ("argumentTypes" to strings(listOf(
                        "id<CodexAgentCodexPlatform> _Nonnull", "CodexAgentCodexClientInfo *",
                    ))))
                    d084FailedConstructorUsr -> JsonObject(reference + ("argumentTypes" to strings(listOf(
                        "CodexAgentCodexWorkspace * _Nullable", "CodexAgentCodexFailure *",
                    ))))
                    else -> reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d085SwiftReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d085WorkspaceUsr) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSbD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val d085ObjectiveCReferenceDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == d085SkillsAvailabilityUsr) {
                    JsonObject(reference + ("receiverType" to JsonPrimitive("CodexAgentCodexPlugins *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val claims = compiler.releaseArray("claims")
        val first = claims.first() as JsonObject
        val swappedClaim = compiler.withArray("claims", JsonArray(listOf(
            JsonObject(first + ("swiftUsr" to JsonPrimitive(CODE_USR))),
        ) + claims.drop(1)))
        val missingClaim = compiler.withArray("claims", JsonArray(claims.dropLast(1)))
        val duplicateClaim = compiler.withArray("claims", JsonArray(claims + claims.first()))
        val d085ClaimIndex = claims.indexOfFirst {
            (it as JsonObject).releaseString("canonicalKey").contains("/CodexSkills.isAvailable|")
        }.also { check(it >= 0) }
        val d085WrongClaim = compiler.withArray("claims", JsonArray(claims.mapIndexed { index, value ->
            if (index == d085ClaimIndex) {
                JsonObject((value as JsonObject) + ("swiftUsr" to JsonPrimitive(d085WorkspaceUsr)))
            } else {
                value
            }
        }))
        val wrongOwnerClaim = compiler.withArray("claims", JsonArray(listOf(
            JsonObject(first + ("canonicalKey" to JsonPrimitive(
                first.releaseString("canonicalKey").replace(APPROVAL_CANONICAL_OWNER, "sample/Foreign"),
            ))),
        ) + claims.drop(1)))
        val cdx = compiler.withObject("surface", run {
            val extra = JsonArray(swift + symbol(
                "c:objc(cs)CDXFailure", "swift", "swift.class", listOf("CDXFailure"), "CDXFailure", "public",
                "class CDXFailure",
            ))
            JsonObject(surface + mapOf(
                "swift" to extra,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(extra)),
            ))
        })
        val wrongArtifact = compiler.withObject(
            "artifacts",
            JsonObject(compiler.releaseObject("artifacts") + ("swiftConsumerSha256" to JsonPrimitive(SHA_F))),
        )
        val duplicateTarget = compiler.withArray(
            "targets",
            JsonArray(compiler.releaseArray("targets") + compiler.releaseArray("targets").first()),
        )
        val failedTests = fixture.xctest.withArray("tests", JsonArray(
            fixture.xctest.releaseArray("tests").mapIndexed { index, value ->
                if (index == 1) JsonObject((value as JsonObject) + ("status" to JsonPrimitive("Failed"))) else value
            },
        ))
        val renamedTests = fixture.xctest.withArray("tests", JsonArray(
            fixture.xctest.releaseArray("tests").mapIndexed { index, value ->
                if (index == 1) JsonObject(
                    (value as JsonObject) + ("identifier" to JsonPrimitive("Other/testChanged()")),
                ) else value
            },
        ))
        val futureCanonical = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) +
                canonicalProperty("future", "kotlin/String!!")).sorted(),
        )
        val overloadedCanonical = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) +
                canonicalConstructor().replace("{}[0]", "{}[1]")).sorted(),
        )
        val futureDecision = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) + canonicalApprovalDecision("FUTURE")).sorted(),
        )
        val futureCollaboration = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) + canonicalCollaborationMode("FUTURE")).sorted(),
        )
        val futureMessageRole = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) + canonicalMessageRole("FUTURE")).sorted(),
        )
        val futureInstallationScope = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) + canonicalInstallationScope("Future")).sorted(),
        )
        val futureMcpEnvironmentSource = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) + canonicalMcpEnvironmentSource("FUTURE")).sorted(),
        )
        val changedConversationId = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) +
                canonicalConversationIdConstructor().replace("kotlin.String", "kotlin.Int")).sorted(),
        )
        val changedAuthorizationFactory = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/CodexAuthorizationUrl.Companion.chatGpt|" in key) {
                    key.replace("suspend=false", "suspend=true")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD077Constructor = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentMcpServer|kind=constructor|" in key) {
                    key.replaceFirst("default=true", "default=false")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD078Constructor = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentMcpTransport.Http|kind=constructor|" in key) {
                    key.replaceFirst("default=true", "default=false")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD079Constructor = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentMessage|kind=constructor|" in key) {
                    key.replaceFirst("default=true", "default=false")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD080Constructor = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentAuthenticationState|kind=constructor|" in key) {
                    key.replaceFirst("default=true", "default=false")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD080Method = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentInteractionState.pendingFor|" in key) {
                    key.replace("return=kotlin.collections/List", "return=kotlin.collections/Set")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD081Object = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentHookHandler.Agent|kind=object|" in key) {
                    key.replace("|kind=object|", "|kind=property|")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD082Method = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentFormField.accepts|" in key) {
                    key.replace("suspend=false", "suspend=true")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD083Property = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/AgentPendingInteraction.conversationId|" in key) {
                    key.replace("ConversationId!!", "ConversationId?")
                } else {
                    key
                }
            }.sorted(),
        )
        val changedD084HostStart = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/CodexHost.start|" in key) key.replace("suspend=true", "suspend=false") else key
            }.sorted(),
        )
        val changedD085Availability = fixture.canonical.copy(
            memberKeys = fixture.canonical.memberKeys.map { key ->
                if ("/CodexSkills.isAvailable|" in key) {
                    key.replace("kotlin/Boolean!!", "kotlin/String!!")
                } else {
                    key
                }
            }.sorted(),
        )

        listOf(
            surfaceDrift, signatureDrift, typeDrift, readonlyDrift, selectorDrift, missingSurface,
            ordinaryEnumDrift, ordinaryConstructorDrift, ordinaryPropertyDrift,
            authorizationFactoryDrift, authorizationPurposeDrift,
            d077ConstructorDrift, d077NullablePropertyDrift, d078ContentIdentifierDrift,
            d079SetIdentifierDrift, d079ConstructorSurfaceDrift,
            d080ConstructorSurfaceDrift, d080MethodSurfaceDrift, d080SetIdentifierDrift,
            d081SharedSurfaceDrift, d082SurfaceDrift, d083SurfaceDrift,
            d084AsyncSurfaceDrift, d084NullableSurfaceDrift,
            d085WorkspaceSurfaceDrift, d085AvailabilitySurfaceDrift,
            duplicateSurface, referenceDrift, swiftReferenceTypeDrift, collaborationReferenceTypeDrift,
            messageRoleReferenceTypeDrift, installationScopeReferenceTypeDrift,
            mcpEnvironmentSourceReferenceTypeDrift, mcpEnvironmentSourceReceiverDrift, qualifierDrift,
            authorizationSwiftReferenceDrift, authorizationObjectiveCReferenceDrift,
            d077SwiftReferenceDrift, d077ObjectiveCConstructorDrift, d077ObjectiveCReceiverDrift,
            d078SwiftReferenceDrift, d078ObjectiveCReceiverDrift,
            d079SwiftReferenceDrift, d079ObjectiveCConstructorDrift,
            d080SwiftMethodReferenceDrift, d080ObjectiveCMethodReferenceDrift,
            d081SwiftReferenceDrift, d081ObjectiveCReferenceDrift,
            d082SwiftReferenceDrift, d082ObjectiveCReferenceDrift,
            d083SwiftReferenceDrift, d083ObjectiveCReferenceDrift,
            d084SwiftReferenceDrift, d084ObjectiveCReferenceDrift,
            d084ObjectiveCConstructorReferenceDrift,
            d085SwiftReferenceDrift, d085ObjectiveCReferenceDrift,
            conversationIdConstructorTypeDrift, conversationIdReceiverDrift,
            swappedClaim, missingClaim, duplicateClaim, d085WrongClaim, wrongOwnerClaim,
            cdx, wrongArtifact, duplicateTarget,
        ).forEach { drift ->
            assertFailsWith<IllegalStateException> { fixture.derive(compiler = drift) }
        }
        listOf(failedTests, renamedTests).forEach { drift ->
            assertFailsWith<IllegalStateException> { fixture.derive(xctest = drift) }
        }
        listOf(
            futureCanonical, overloadedCanonical, futureDecision, futureCollaboration, futureMessageRole,
            futureInstallationScope, futureMcpEnvironmentSource, changedConversationId,
            changedAuthorizationFactory, changedD077Constructor, changedD078Constructor, changedD079Constructor,
            changedD080Constructor, changedD080Method, changedD081Object, changedD082Method,
            changedD083Property, changedD084HostStart, changedD085Availability,
        )
            .forEach { drift ->
            assertFailsWith<IllegalStateException> { fixture.derive(canonical = drift) }
        }
        assertFailsWith<IllegalStateException> {
            fixture.derive(digests = fixture.digests.copy(xcresultSha256 = SHA_B))
        }
    }

    @Test
    fun `task is cacheable and deletes stale output before malformed inputs`() = withRoot { root ->
        val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
            "appleBindingEvidence",
            GenerateAppleBindingEvidenceTask::class.java,
        )
        val missing = root.resolve("missing")
        task.canonicalApiReport.set(missing.resolve("canonical-api.json"))
        task.canonicalCoverageReceipt.set(missing.resolve("canonical-coverage.json"))
        task.compilerEvidence.set(missing.resolve("compiler-evidence.json"))
        task.xcframeworkDirectory.set(missing.resolve("CodexAgent.xcframework"))
        task.swiftConsumer.set(missing.resolve("consumer.swift"))
        task.objectiveCConsumer.set(missing.resolve("consumer.m"))
        task.xctestEvidence.set(missing.resolve("xctest.json"))
        task.xcresultDirectory.set(missing.resolve("tests.xcresult"))
        val output = root.resolve("binding-evidence.json").apply { writeText("stale observed evidence") }
        task.evidenceFile.set(output)

        assertTrue(GenerateAppleBindingEvidenceTask::class.java.isAnnotationPresent(CacheableTask::class.java))
        assertFailsWith<IllegalStateException> { task.generate() }
        assertFalse(output.exists())
    }

    @Test
    fun `iOS plugin registers only observed Apple evidence with stale invalidation`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("build.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
        val registration = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts",
        ).readText()

        listOf(
            "invalidateCodexAgentAppleBindingEvidence",
            "generateCodexAgentAppleBindingEvidence",
            "GenerateAppleBindingEvidenceTask",
            "reports/cross-language-api/apple/binding-evidence.json",
            "appleCompilerEvidence.flatMap(AppleCompilerEvidenceTask::evidenceFile)",
            "VerifySwiftAuthenticationTestsTask::summaryFile",
            "VerifySwiftAuthenticationTestsTask::resultBundleDirectory",
        ).forEach { expected -> assertTrue(expected in registration) }
        assertFalse("swift-parity.json" in registration)
        assertFalse("objective-c-parity.json" in registration)
    }

    private data class Fixture(
        val canonical: CrossLanguageCanonicalApiEvidence,
        val compiler: JsonObject,
        val xctest: JsonObject,
        val digests: AppleBindingInputDigests,
    ) {
        val capabilities = appleBindingCapabilityKeys(canonical.memberKeys)

        fun derive(
            canonical: CrossLanguageCanonicalApiEvidence = this.canonical,
            compiler: JsonObject = this.compiler,
            xctest: JsonObject = this.xctest,
            digests: AppleBindingInputDigests = this.digests,
        ) = deriveCrossLanguageAppleBindingEvidence(canonical, compiler, xctest, digests)
    }

    private fun fixture(): Fixture {
        val members = (listOf(
            canonicalConstructor(),
            canonicalProperty("code", "kotlin/String!!"),
            canonicalProperty("isRecoverable", "kotlin/Boolean!!"),
            canonicalProperty("message", "kotlin/String!!"),
            canonicalApprovalDecision("ACCEPT"),
            canonicalApprovalDecision("DECLINE"),
            canonicalCollaborationMode("DEFAULT"),
            canonicalCollaborationMode("PLAN"),
            canonicalMessageRole("USER"),
            canonicalMessageRole("ASSISTANT"),
            canonicalInstallationScope("User"),
            canonicalInstallationScope("Workspace"),
            canonicalMcpEnvironmentSource("LOCAL"),
            canonicalMcpEnvironmentSource("REMOTE"),
            canonicalConversationIdConstructor(),
            canonicalProperty("value", "kotlin/String!!", owner = "ConversationId"),
        ) + appleCompilerFixtureD065Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD073Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD074Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD075Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD076Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD077Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD078Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD079Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD080Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD081Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD082Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD083Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD084Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD085Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            (0 until 57).map { index ->
                "common|owner=sample/Owner${index.toString().padStart(3, '0')}|kind=property|" +
                    "abi=sample/Owner$index.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!"
            }).sorted()
        val canonical = CrossLanguageCanonicalApiEvidence(
            members,
            CrossLanguageBindingCanonicalIdentity(SHA_A, SHA_B),
            mapOf("native" to SHA_C, "wasm" to SHA_D, "jvm-classes" to SHA_E),
            SHA_D,
            SHA_E,
            setOf("canonical/test"),
        )
        val capabilities = appleBindingCapabilityKeys(members)
        val targetDigests = linkedMapOf(
            "ios-arm64" to AppleBindingTargetDigests(SHA_A, SHA_B, SHA_C, SHA_D),
            "ios-arm64-simulator" to AppleBindingTargetDigests(SHA_E, SHA_F, SHA_C, SHA_D),
        )
        val swift = swiftSurface()
        val objectiveC = objectiveCSurface()
        val swiftReferences = swiftReferences()
        val objectiveCReferences = objectiveCReferences()
        val compiler = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive(APPLE_COMPILER_EVIDENCE_PROTOCOL))
            put("result", JsonPrimitive("observed"))
            put("moduleName", JsonPrimitive("CodexAgent"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive(SHA_A))
                put("coverageReceiptSha256", JsonPrimitive(SHA_B))
                put("nativeTargetSha256", JsonPrimitive(SHA_C))
                put("capabilities", strings(capabilities))
            })
            put("toolchain", buildJsonObject {
                put("xcodeVersion", JsonPrimitive("26.6"))
                put("xcodeBuild", JsonPrimitive("17F113"))
                put("swiftVersion", JsonPrimitive("6.3.3"))
                put("clangVersion", JsonPrimitive("Apple clang version 21.0.0"))
            })
            put("artifacts", buildJsonObject {
                put("xcframeworkSha256", JsonPrimitive(SHA_A))
                put("swiftConsumerSha256", JsonPrimitive(SHA_B))
                put("objectiveCConsumerSha256", JsonPrimitive(SHA_C))
            })
            put("targets", buildJsonArray {
                add(target("ios-arm64", "iphoneos", "arm64-apple-ios15.0", targetDigests.getValue("ios-arm64")))
                add(target(
                    "ios-arm64-simulator", "iphonesimulator", "arm64-apple-ios15.0-simulator",
                    targetDigests.getValue("ios-arm64-simulator"),
                ))
            })
            put("surface", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swift)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveC)))
                put("swift", swift)
                put("objectiveC", objectiveC)
            })
            put("references", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swiftReferences)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveCReferences)))
                put("swift", swiftReferences)
                put("objectiveC", objectiveCReferences)
            })
            put("claims", buildJsonArray {
                capabilities.forEach { capability ->
                    val usr = usr(capability)
                    add(buildJsonObject {
                        put("canonicalKey", JsonPrimitive(capability))
                        put("swiftUsr", JsonPrimitive(usr))
                        put("objectiveCUsr", JsonPrimitive(usr))
                    })
                }
            })
        }
        val tests = listOf(
            "CodexAgentObservationTests/testBufferingCancellationAndDroppedStreamReleaseTheObservation()",
            SWIFT_FAILURE_TEST,
            OBJECTIVE_C_FAILURE_TEST,
            "CodexAuthorizationBrowserTests/testGenericBrowserOpensTypedExternalURLAndCancelsPresentation()",
        ).sorted()
        val xctest = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive("codex-agent-apple-xctest-v1"))
            put("result", JsonPrimitive("passed"))
            put("totalTestCount", JsonPrimitive(4))
            put("failedTests", JsonPrimitive(0))
            put("xcresultSha256", JsonPrimitive(SHA_D))
            put("tests", buildJsonArray { tests.forEach { test -> add(buildJsonObject {
                put("identifier", JsonPrimitive(test)); put("status", JsonPrimitive("Passed"))
            }) } })
        }
        return Fixture(
            canonical,
            compiler,
            xctest,
            AppleBindingInputDigests(SHA_E, SHA_A, SHA_B, SHA_C, SHA_F, SHA_D, targetDigests),
        )
    }

    private fun swiftSurface() = JsonArray((listOf(
        symbol(OWNER, "swift", "swift.class", listOf("CodexFailure"), "CodexFailure", "public", "class CodexFailure"),
        symbol(
            CONSTRUCTOR, "swift", "swift.init", listOf("CodexFailure", "init(code:message:isRecoverable:)"),
            "init(code:message:isRecoverable:)", "public",
            "init(code: String, message: String, isRecoverable: Bool)",
            listOf("s:SS", "s:SS", "s:Sb"),
            listOf("code" to "code: String", "message" to "message: String", "isRecoverable" to "isRecoverable: Bool"),
        ),
        symbol(CODE_USR, "swift", "swift.property", listOf("CodexFailure", "code"), "code", "open",
            "var code: String { get }", listOf("s:SS")),
        symbol(RECOVERABLE_USR, "swift", "swift.property", listOf("CodexFailure", "isRecoverable"),
            "isRecoverable", "open", "var isRecoverable: Bool { get }", listOf("s:Sb")),
        symbol(MESSAGE_USR, "swift", "swift.property", listOf("CodexFailure", "message"), "message", "open",
            "var message: String { get }", listOf("s:SS")),
        symbol(CONVERSATION_ID_OWNER, "swift", "swift.class", listOf("ConversationId"),
            "ConversationId", "public", "class ConversationId"),
        symbol(CONVERSATION_ID_CONSTRUCTOR_USR, "swift", "swift.init",
            listOf("ConversationId", "init(value:)"), "init(value:)", "public",
            "init(value: String)", listOf("s:SS"), listOf("value" to "value: String")),
        symbol(CONVERSATION_ID_VALUE_USR, "swift", "swift.property", listOf("ConversationId", "value"),
            "value", "open", "var value: String { get }", listOf("s:SS")),
        symbol(APPROVAL_OWNER, "swift", "swift.class", listOf("AgentApprovalDecision"),
            "AgentApprovalDecision", "public", "class AgentApprovalDecision"),
        symbol(ACCEPT_USR, "swift", "swift.type.property", listOf("AgentApprovalDecision", "accept"),
            "accept", "open", "class var accept: AgentApprovalDecision { get }", listOf(APPROVAL_OWNER)),
        symbol(DECLINE_USR, "swift", "swift.type.property", listOf("AgentApprovalDecision", "decline"),
            "decline", "open", "class var decline: AgentApprovalDecision { get }", listOf(APPROVAL_OWNER)),
        symbol(COLLABORATION_OWNER, "swift", "swift.class", listOf("AgentCollaborationMode"),
            "AgentCollaborationMode", "public", "class AgentCollaborationMode"),
        symbol(DEFAULT_USR, "swift", "swift.type.property", listOf("AgentCollaborationMode", "default_"),
            "default_", "open", "class var default_: AgentCollaborationMode { get }", listOf(COLLABORATION_OWNER)),
        symbol(PLAN_USR, "swift", "swift.type.property", listOf("AgentCollaborationMode", "plan"),
            "plan", "open", "class var plan: AgentCollaborationMode { get }", listOf(COLLABORATION_OWNER)),
        symbol(MESSAGE_ROLE_OWNER, "swift", "swift.class", listOf("AgentMessageRole"),
            "AgentMessageRole", "public", "class AgentMessageRole"),
        symbol(USER_USR, "swift", "swift.type.property", listOf("AgentMessageRole", "user"),
            "user", "open", "class var user: AgentMessageRole { get }", listOf(MESSAGE_ROLE_OWNER)),
        symbol(ASSISTANT_USR, "swift", "swift.type.property", listOf("AgentMessageRole", "assistant"),
            "assistant", "open", "class var assistant: AgentMessageRole { get }", listOf(MESSAGE_ROLE_OWNER)),
        symbol(INSTALLATION_SCOPE_OWNER, "swift", "swift.class", listOf("AgentInstallationScope"),
            "AgentInstallationScope", "public", "class AgentInstallationScope"),
        symbol(INSTALLATION_USER_USR, "swift", "swift.type.property", listOf("AgentInstallationScope", "user"),
            "user", "open", "class var user: AgentInstallationScope { get }", listOf(INSTALLATION_SCOPE_OWNER)),
        symbol(
            INSTALLATION_WORKSPACE_USR, "swift", "swift.type.property",
            listOf("AgentInstallationScope", "workspace"), "workspace", "open",
            "class var workspace: AgentInstallationScope { get }", listOf(INSTALLATION_SCOPE_OWNER),
        ),
        symbol(MCP_ENVIRONMENT_SOURCE_OWNER, "swift", "swift.class", listOf("AgentMcpEnvironmentSource"),
            "AgentMcpEnvironmentSource", "public", "class AgentMcpEnvironmentSource"),
        symbol(MCP_ENVIRONMENT_LOCAL_USR, "swift", "swift.type.property",
            listOf("AgentMcpEnvironmentSource", "local"), "local", "open",
            "class var local: AgentMcpEnvironmentSource { get }", listOf(MCP_ENVIRONMENT_SOURCE_OWNER)),
        symbol(MCP_ENVIRONMENT_REMOTE_USR, "swift", "swift.type.property",
            listOf("AgentMcpEnvironmentSource", "remote"), "remote", "open",
            "class var remote: AgentMcpEnvironmentSource { get }", listOf(MCP_ENVIRONMENT_SOURCE_OWNER)),
    ) + appleCompilerFixtureD065SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD073SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD074SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD075SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD076SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD077SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD078SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD079SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD080SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD081SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD082SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD083SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD084SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    } + appleCompilerFixtureD085SwiftSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "swift", expected)
    }).sortedBy { it.releaseString("precise") })

    private fun objectiveCSurface() = JsonArray((listOf(
        symbol(OWNER, "objective-c", "objective-c.class", listOf("CodexAgentCodexFailure"),
            "CodexAgentCodexFailure", "public", "@interface CodexAgentCodexFailure : CodexAgentBase",
            listOf("c:objc(cs)CodexAgentBase")),
        symbol(
            CONSTRUCTOR, "objective-c", "objective-c.method",
            listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
            "initWithCode:message:isRecoverable:", "public",
            "- (instancetype) initWithCode:(NSString *) code message:(NSString *) message " +
                "isRecoverable:(BOOL) isRecoverable;",
            listOf("c:objc(cs)NSString", "c:objc(cs)NSString", "c:@T@BOOL"),
            listOf("code" to "(NSString *) code", "message" to "(NSString *) message",
                "isRecoverable" to "(BOOL) isRecoverable"),
            "instancetype",
        ),
        symbol(CODE_USR, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "code"),
            "code", "public", "@property (readonly) NSString * code;", listOf("c:objc(cs)NSString")),
        symbol(RECOVERABLE_USR, "objective-c", "objective-c.property",
            listOf("CodexAgentCodexFailure", "isRecoverable"), "isRecoverable", "public",
            "@property (readonly) BOOL isRecoverable;", listOf("c:@T@BOOL")),
        symbol(MESSAGE_USR, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "message"),
            "message", "public", "@property (readonly) NSString * message;", listOf("c:objc(cs)NSString")),
        symbol(CONVERSATION_ID_OWNER, "objective-c", "objective-c.class", listOf("CodexAgentConversationId"),
            "CodexAgentConversationId", "public", "@interface CodexAgentConversationId : CodexAgentBase",
            listOf("c:objc(cs)CodexAgentBase")),
        symbol(CONVERSATION_ID_CONSTRUCTOR_USR, "objective-c", "objective-c.method",
            listOf("CodexAgentConversationId", "initWithValue:"), "initWithValue:", "public",
            "- (instancetype) initWithValue:(NSString *) value;", listOf("c:objc(cs)NSString"),
            listOf("value" to "(NSString *) value"), "instancetype"),
        symbol(CONVERSATION_ID_VALUE_USR, "objective-c", "objective-c.property",
            listOf("CodexAgentConversationId", "value"), "value", "public",
            "@property (readonly) NSString * value;", listOf("c:objc(cs)NSString")),
        symbol(APPROVAL_OWNER, "objective-c", "objective-c.class", listOf("CodexAgentAgentApprovalDecision"),
            "CodexAgentAgentApprovalDecision", "public",
            "@interface CodexAgentAgentApprovalDecision : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum")),
        symbol(ACCEPT_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentApprovalDecision", "accept"), "accept", "public",
            "@property (class, readonly) CodexAgentAgentApprovalDecision * accept;", listOf(APPROVAL_OWNER)),
        symbol(DECLINE_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentApprovalDecision", "decline"), "decline", "public",
            "@property (class, readonly) CodexAgentAgentApprovalDecision * decline;", listOf(APPROVAL_OWNER)),
        symbol(COLLABORATION_OWNER, "objective-c", "objective-c.class",
            listOf("CodexAgentAgentCollaborationMode"), "CodexAgentAgentCollaborationMode", "public",
            "@interface CodexAgentAgentCollaborationMode : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum")),
        symbol(DEFAULT_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentCollaborationMode", "default_"), "default_", "public",
            "@property (class, readonly) CodexAgentAgentCollaborationMode * default_;",
            listOf(COLLABORATION_OWNER)),
        symbol(PLAN_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentCollaborationMode", "plan"), "plan", "public",
            "@property (class, readonly) CodexAgentAgentCollaborationMode * plan;",
            listOf(COLLABORATION_OWNER)),
        symbol(MESSAGE_ROLE_OWNER, "objective-c", "objective-c.class",
            listOf("CodexAgentAgentMessageRole"), "CodexAgentAgentMessageRole", "public",
            "@interface CodexAgentAgentMessageRole : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum")),
        symbol(USER_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentMessageRole", "user"), "user", "public",
            "@property (class, readonly) CodexAgentAgentMessageRole * user;", listOf(MESSAGE_ROLE_OWNER)),
        symbol(ASSISTANT_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentMessageRole", "assistant"), "assistant", "public",
            "@property (class, readonly) CodexAgentAgentMessageRole * assistant;", listOf(MESSAGE_ROLE_OWNER)),
        symbol(INSTALLATION_SCOPE_OWNER, "objective-c", "objective-c.class",
            listOf("CodexAgentAgentInstallationScope"), "CodexAgentAgentInstallationScope", "public",
            "@interface CodexAgentAgentInstallationScope : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum")),
        symbol(INSTALLATION_USER_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentInstallationScope", "user"), "user", "public",
            "@property (class, readonly) CodexAgentAgentInstallationScope * user;",
            listOf(INSTALLATION_SCOPE_OWNER)),
        symbol(INSTALLATION_WORKSPACE_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentInstallationScope", "workspace"), "workspace", "public",
            "@property (class, readonly) CodexAgentAgentInstallationScope * workspace;",
            listOf(INSTALLATION_SCOPE_OWNER)),
        symbol(MCP_ENVIRONMENT_SOURCE_OWNER, "objective-c", "objective-c.class",
            listOf("CodexAgentAgentMcpEnvironmentSource"), "CodexAgentAgentMcpEnvironmentSource", "public",
            "@interface CodexAgentAgentMcpEnvironmentSource : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum")),
        symbol(MCP_ENVIRONMENT_LOCAL_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentMcpEnvironmentSource", "local"), "local", "public",
            "@property (class, readonly) CodexAgentAgentMcpEnvironmentSource * local;",
            listOf(MCP_ENVIRONMENT_SOURCE_OWNER)),
        symbol(MCP_ENVIRONMENT_REMOTE_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentMcpEnvironmentSource", "remote"), "remote", "public",
            "@property (class, readonly) CodexAgentAgentMcpEnvironmentSource * remote;",
            listOf(MCP_ENVIRONMENT_SOURCE_OWNER)),
    ) + appleCompilerFixtureD065ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD073ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD074ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD075ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD076ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD077ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD078ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD079ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD080ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD081ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD082ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD083ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD084ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    } + appleCompilerFixtureD085ObjectiveCSymbols().map { (precise, expected) ->
        expectedSymbol(precise, "objective-c", expected)
    }).sortedBy { it.releaseString("precise") })

    private fun swiftReferences() = JsonArray((listOf(
        reference(CONSTRUCTOR, "declref_expr", "init", null, "\$sySo010CodexAgentA7FailureCSS_SSSbtcABmcD"),
        reference(CODE_USR, "member_ref_expr", "code", null, "\$sSSD"),
        reference(RECOVERABLE_USR, "member_ref_expr", "isRecoverable", null, "\$sSbD"),
        reference(MESSAGE_USR, "member_ref_expr", "message", null, "\$sSSD"),
        reference(CONVERSATION_ID_CONSTRUCTOR_USR, "declref_expr", "init", null,
            CONVERSATION_ID_SWIFT_CONSTRUCTOR_TYPE),
        reference(CONVERSATION_ID_VALUE_USR, "member_ref_expr", "value", null, "\$sSSD"),
        reference(ACCEPT_USR, "member_ref_expr", "accept", null, APPROVAL_SWIFT_TYPE),
        reference(DECLINE_USR, "member_ref_expr", "decline", null, APPROVAL_SWIFT_TYPE),
        reference(DEFAULT_USR, "member_ref_expr", "default_", null, COLLABORATION_SWIFT_TYPE),
        reference(PLAN_USR, "member_ref_expr", "plan", null, COLLABORATION_SWIFT_TYPE),
        reference(USER_USR, "member_ref_expr", "user", null, MESSAGE_ROLE_SWIFT_TYPE),
        reference(ASSISTANT_USR, "member_ref_expr", "assistant", null, MESSAGE_ROLE_SWIFT_TYPE),
        reference(INSTALLATION_USER_USR, "member_ref_expr", "user", null, INSTALLATION_SCOPE_SWIFT_TYPE),
        reference(
            INSTALLATION_WORKSPACE_USR, "member_ref_expr", "workspace", null, INSTALLATION_SCOPE_SWIFT_TYPE,
        ),
        reference(MCP_ENVIRONMENT_LOCAL_USR, "member_ref_expr", "local", null, MCP_ENVIRONMENT_SOURCE_SWIFT_TYPE),
        reference(
            MCP_ENVIRONMENT_REMOTE_USR, "member_ref_expr", "remote", null, MCP_ENVIRONMENT_SOURCE_SWIFT_TYPE,
        ),
    ) + appleCompilerFixtureSwiftReferences()
        .filter { it.precise in (appleCompilerFixtureD065Capabilities + appleCompilerFixtureD073Capabilities +
            appleCompilerFixtureD074Capabilities + appleCompilerFixtureD075Capabilities +
            appleCompilerFixtureD076Capabilities + appleCompilerFixtureD077Capabilities +
            appleCompilerFixtureD078Capabilities + appleCompilerFixtureD079Capabilities +
            appleCompilerFixtureD080Capabilities + appleCompilerFixtureD081Capabilities +
            appleCompilerFixtureD082Capabilities + appleCompilerFixtureD083Capabilities +
            appleCompilerFixtureD084Capabilities + appleCompilerFixtureD085Capabilities)
            .map(AppleOrdinaryCapability::usr) }
        .map(::expectedReference)
    ).sortedBy { it.releaseString("precise") })

    private fun objectiveCReferences() = JsonArray((listOf(
        reference(CONSTRUCTOR, "ObjCMessageExpr", "initWithCode:message:isRecoverable:",
            "CodexAgentCodexFailure", "CodexAgentCodexFailure *", listOf("NSString *", "NSString *", "BOOL")),
        reference(CODE_USR, "ObjCPropertyRefExpr", "code", "CodexAgentCodexFailure *", "<pseudo-object type>"),
        reference(RECOVERABLE_USR, "ObjCPropertyRefExpr", "isRecoverable", "CodexAgentCodexFailure *",
            "<pseudo-object type>"),
        reference(MESSAGE_USR, "ObjCPropertyRefExpr", "message", "CodexAgentCodexFailure *", "<pseudo-object type>"),
        reference(CONVERSATION_ID_CONSTRUCTOR_USR, "ObjCMessageExpr", "initWithValue:",
            "CodexAgentConversationId", "CodexAgentConversationId *", listOf("NSString *")),
        reference(CONVERSATION_ID_VALUE_USR, "ObjCPropertyRefExpr", "value", "CodexAgentConversationId *",
            "<pseudo-object type>"),
        reference(ACCEPT_USR, "ObjCMessageExpr", "accept", "CodexAgentAgentApprovalDecision",
            "CodexAgentAgentApprovalDecision * _Nonnull"),
        reference(DECLINE_USR, "ObjCMessageExpr", "decline", "CodexAgentAgentApprovalDecision",
            "CodexAgentAgentApprovalDecision * _Nonnull"),
        reference(DEFAULT_USR, "ObjCMessageExpr", "default_", "CodexAgentAgentCollaborationMode",
            "CodexAgentAgentCollaborationMode * _Nonnull"),
        reference(PLAN_USR, "ObjCMessageExpr", "plan", "CodexAgentAgentCollaborationMode",
            "CodexAgentAgentCollaborationMode * _Nonnull"),
        reference(USER_USR, "ObjCMessageExpr", "user", "CodexAgentAgentMessageRole",
            "CodexAgentAgentMessageRole * _Nonnull"),
        reference(ASSISTANT_USR, "ObjCMessageExpr", "assistant", "CodexAgentAgentMessageRole",
            "CodexAgentAgentMessageRole * _Nonnull"),
        reference(INSTALLATION_USER_USR, "ObjCMessageExpr", "user", "CodexAgentAgentInstallationScope",
            "CodexAgentAgentInstallationScope * _Nonnull"),
        reference(INSTALLATION_WORKSPACE_USR, "ObjCMessageExpr", "workspace", "CodexAgentAgentInstallationScope",
            "CodexAgentAgentInstallationScope * _Nonnull"),
        reference(MCP_ENVIRONMENT_LOCAL_USR, "ObjCMessageExpr", "local", "CodexAgentAgentMcpEnvironmentSource",
            "CodexAgentAgentMcpEnvironmentSource * _Nonnull"),
        reference(MCP_ENVIRONMENT_REMOTE_USR, "ObjCMessageExpr", "remote", "CodexAgentAgentMcpEnvironmentSource",
            "CodexAgentAgentMcpEnvironmentSource * _Nonnull"),
    ) + appleCompilerFixtureObjectiveCReferences()
        .filter { it.precise in (appleCompilerFixtureD065Capabilities + appleCompilerFixtureD073Capabilities +
            appleCompilerFixtureD074Capabilities + appleCompilerFixtureD075Capabilities +
            appleCompilerFixtureD076Capabilities + appleCompilerFixtureD077Capabilities +
            appleCompilerFixtureD078Capabilities + appleCompilerFixtureD079Capabilities +
            appleCompilerFixtureD080Capabilities + appleCompilerFixtureD081Capabilities +
            appleCompilerFixtureD082Capabilities + appleCompilerFixtureD083Capabilities +
            appleCompilerFixtureD084Capabilities + appleCompilerFixtureD085Capabilities)
            .map(AppleOrdinaryCapability::usr) }
        .map(::expectedReference)
    ).sortedBy { it.releaseString("precise") })

    private fun expectedSymbol(
        precise: String,
        language: String,
        expected: ExpectedAppleCompilerSymbol,
    ) = symbol(
        precise,
        language,
        expected.kind,
        expected.path,
        expected.title,
        expected.access,
        expected.declaration,
        expected.typeIdentifiers,
        expected.parameters,
        expected.returns,
    )

    private fun expectedReference(expected: AppleCompilerReference) = reference(
        expected.precise,
        expected.kind,
        expected.name,
        expected.receiverType,
        expected.valueType,
        expected.argumentTypes,
    )

    private fun symbol(
        precise: String,
        language: String,
        kind: String,
        path: List<String>,
        title: String,
        access: String,
        declaration: String,
        types: List<String> = emptyList(),
        parameters: List<Pair<String, String>> = emptyList(),
        returns: String? = null,
    ) = buildJsonObject {
        put("precise", JsonPrimitive(precise)); put("interfaceLanguage", JsonPrimitive(language))
        put("kind", JsonPrimitive(kind)); put("path", strings(path)); put("title", JsonPrimitive(title))
        put("accessLevel", JsonPrimitive(access)); put("declaration", JsonPrimitive(declaration))
        put("typeIdentifiers", strings(types)); put("parameters", buildJsonArray {
            parameters.forEach { (name, value) -> add(buildJsonObject {
                put("name", JsonPrimitive(name)); put("declaration", JsonPrimitive(value))
            }) }
        })
        put("returns", returns?.let(::JsonPrimitive) ?: JsonNull)
    }

    private fun reference(
        precise: String,
        kind: String,
        name: String,
        receiverType: String?,
        valueType: String,
        argumentTypes: List<String> = emptyList(),
    ) = buildJsonObject {
        put("precise", JsonPrimitive(precise)); put("kind", JsonPrimitive(kind)); put("name", JsonPrimitive(name))
        put("receiverType", receiverType?.let(::JsonPrimitive) ?: JsonNull)
        put("valueType", JsonPrimitive(valueType)); put("argumentTypes", strings(argumentTypes))
    }

    private fun target(name: String, sdk: String, triple: String, digests: AppleBindingTargetDigests) =
        buildJsonObject {
            put("name", JsonPrimitive(name)); put("sdk", JsonPrimitive(sdk)); put("sdkVersion", JsonPrimitive("26.5"))
            put("targetTriple", JsonPrimitive(triple)); put("frameworkSha256", JsonPrimitive(digests.frameworkSha256))
            put("binarySha256", JsonPrimitive(digests.binarySha256)); put("headerSha256", JsonPrimitive(digests.headerSha256))
            put("moduleMapSha256", JsonPrimitive(digests.moduleMapSha256))
        }

    private fun usr(capability: String): String =
        (appleCompilerFixtureD065Capabilities + appleCompilerFixtureD073Capabilities +
            appleCompilerFixtureD074Capabilities + appleCompilerFixtureD075Capabilities +
            appleCompilerFixtureD076Capabilities + appleCompilerFixtureD077Capabilities +
            appleCompilerFixtureD078Capabilities + appleCompilerFixtureD079Capabilities +
            appleCompilerFixtureD080Capabilities + appleCompilerFixtureD081Capabilities +
            appleCompilerFixtureD082Capabilities + appleCompilerFixtureD083Capabilities +
            appleCompilerFixtureD084Capabilities + appleCompilerFixtureD085Capabilities)
            .singleOrNull { it.canonicalKey == capability }?.usr ?: when {
        "|owner=$CANONICAL_OWNER|kind=constructor|" in capability -> CONSTRUCTOR
        "|owner=$CONVERSATION_ID_CANONICAL_OWNER|kind=constructor|" in capability ->
            CONVERSATION_ID_CONSTRUCTOR_USR
        "|owner=$CONVERSATION_ID_CANONICAL_OWNER|kind=property|" in capability &&
            "|{}value[0]|" in capability -> CONVERSATION_ID_VALUE_USR
        "|{}code[0]|" in capability -> CODE_USR
        "|{}isRecoverable[0]|" in capability -> RECOVERABLE_USR
        "|{}message[0]|" in capability -> MESSAGE_USR
        ".ACCEPT|null[0]" in capability -> ACCEPT_USR
        ".DECLINE|null[0]" in capability -> DECLINE_USR
        ".DEFAULT|null[0]" in capability -> DEFAULT_USR
        ".PLAN|null[0]" in capability -> PLAN_USR
        ".USER|null[0]" in capability -> USER_USR
        ".ASSISTANT|null[0]" in capability -> ASSISTANT_USR
        ".User|null[0]" in capability -> INSTALLATION_USER_USR
        ".Workspace|null[0]" in capability -> INSTALLATION_WORKSPACE_USR
        ".LOCAL|null[0]" in capability -> MCP_ENVIRONMENT_LOCAL_USR
        ".REMOTE|null[0]" in capability -> MCP_ENVIRONMENT_REMOTE_USR
        else -> error("Unexpected Apple binding fixture capability: $capability")
    }

    private fun canonicalConstructor(): String =
        "common|owner=$CANONICAL_OWNER|kind=constructor|abi=$CANONICAL_OWNER.<init>|" +
            "<init>(kotlin.String;kotlin.String;kotlin.Boolean){}[0]|return=$CANONICAL_OWNER|suspend=false|" +
            "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false," +
            "REGULAR:kotlin/String!!:default=false:vararg=false," +
            "REGULAR:kotlin/Boolean!!:default=false:vararg=false]"

    private fun canonicalProperty(name: String, type: String, owner: String = "CodexFailure"): String {
        val canonicalOwner = "io.github.codex_agent_labs.codexmobile.agent/$owner"
        return "common|owner=$canonicalOwner|kind=property|abi=$canonicalOwner.$name|{}$name[0]|" +
            "propertyKind=VAL|type=$type"
    }

    private fun canonicalConversationIdConstructor(): String =
        "common|owner=$CONVERSATION_ID_CANONICAL_OWNER|kind=constructor|" +
            "abi=$CONVERSATION_ID_CANONICAL_OWNER.<init>|<init>(kotlin.String){}[0]|" +
            "return=$CONVERSATION_ID_CANONICAL_OWNER|suspend=false|" +
            "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]"

    private fun canonicalApprovalDecision(name: String): String =
        "common|owner=$APPROVAL_CANONICAL_OWNER|kind=enum-entry|" +
            "abi=$APPROVAL_CANONICAL_OWNER.$name|null[0]"

    private fun canonicalCollaborationMode(name: String): String =
        "common|owner=$COLLABORATION_CANONICAL_OWNER|kind=enum-entry|" +
            "abi=$COLLABORATION_CANONICAL_OWNER.$name|null[0]"

    private fun canonicalMessageRole(name: String): String =
        "common|owner=$MESSAGE_ROLE_CANONICAL_OWNER|kind=enum-entry|" +
            "abi=$MESSAGE_ROLE_CANONICAL_OWNER.$name|null[0]"

    private fun canonicalInstallationScope(name: String): String =
        "common|owner=$INSTALLATION_SCOPE_CANONICAL_OWNER|kind=enum-entry|" +
            "abi=$INSTALLATION_SCOPE_CANONICAL_OWNER.$name|null[0]"

    private fun canonicalMcpEnvironmentSource(name: String): String =
        "common|owner=$MCP_ENVIRONMENT_SOURCE_CANONICAL_OWNER|kind=enum-entry|" +
            "abi=$MCP_ENVIRONMENT_SOURCE_CANONICAL_OWNER.$name|null[0]"

    private fun strings(values: Iterable<String>) = buildJsonArray { values.forEach { add(JsonPrimitive(it)) } }
    private fun JsonObject.withObject(name: String, value: JsonObject) = JsonObject(this + (name to value))
    private fun JsonObject.withArray(name: String, value: JsonArray) = JsonObject(this + (name to value))
    private fun JsonObject.surfaceDrift(
        language: String,
        index: Int,
        field: String,
        value: JsonElement,
    ): JsonObject {
        val surface = releaseObject("surface")
        val changed = JsonArray(surface.releaseArray(language).mapIndexed { itemIndex, item ->
            if (itemIndex == index) JsonObject((item as JsonObject) + (field to value)) else item
        })
        val digestField = if (language == "swift") "swiftSha256" else "objectiveCSha256"
        return withObject("surface", JsonObject(surface + mapOf(
            language to changed,
            digestField to JsonPrimitive(appleCompilerJsonDigest(changed)),
        )))
    }

    private fun withRoot(block: (File) -> Unit) {
        val root = createTempDirectory("apple-binding-evidence").toFile()
        try {
            block(root)
        } finally {
            root.deleteRecursively()
        }
    }

    private companion object {
        const val CANONICAL_OWNER = "io.github.codex_agent_labs.codexmobile.agent/CodexFailure"
        const val OWNER = "c:objc(cs)CodexAgentCodexFailure"
        const val CONSTRUCTOR = "$OWNER(im)initWithCode:message:isRecoverable:"
        const val CODE_USR = "$OWNER(py)code"
        const val RECOVERABLE_USR = "$OWNER(py)isRecoverable"
        const val MESSAGE_USR = "$OWNER(py)message"
        const val CONVERSATION_ID_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/ConversationId"
        const val CONVERSATION_ID_OWNER = "c:objc(cs)CodexAgentConversationId"
        const val CONVERSATION_ID_CONSTRUCTOR_USR = "$CONVERSATION_ID_OWNER(im)initWithValue:"
        const val CONVERSATION_ID_VALUE_USR = "$CONVERSATION_ID_OWNER(py)value"
        const val CONVERSATION_ID_SWIFT_CONSTRUCTOR_TYPE =
            "\$sySo24CodexAgentConversationIdCSS_tcABmcD"
        const val APPROVAL_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision"
        const val APPROVAL_OWNER = "c:objc(cs)CodexAgentAgentApprovalDecision"
        const val ACCEPT_USR = "$APPROVAL_OWNER(cpy)accept"
        const val DECLINE_USR = "$APPROVAL_OWNER(cpy)decline"
        const val APPROVAL_SWIFT_TYPE = "\$sSo010CodexAgentB16ApprovalDecisionCD"
        const val COLLABORATION_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode"
        const val COLLABORATION_OWNER = "c:objc(cs)CodexAgentAgentCollaborationMode"
        const val DEFAULT_USR = "$COLLABORATION_OWNER(cpy)default_"
        const val PLAN_USR = "$COLLABORATION_OWNER(cpy)plan"
        const val COLLABORATION_SWIFT_TYPE = "\$sSo010CodexAgentB17CollaborationModeCD"
        const val MESSAGE_ROLE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole"
        const val MESSAGE_ROLE_OWNER = "c:objc(cs)CodexAgentAgentMessageRole"
        const val USER_USR = "$MESSAGE_ROLE_OWNER(cpy)user"
        const val ASSISTANT_USR = "$MESSAGE_ROLE_OWNER(cpy)assistant"
        const val MESSAGE_ROLE_SWIFT_TYPE = "\$sSo010CodexAgentB11MessageRoleCD"
        const val INSTALLATION_SCOPE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope"
        const val INSTALLATION_SCOPE_OWNER = "c:objc(cs)CodexAgentAgentInstallationScope"
        const val INSTALLATION_USER_USR = "$INSTALLATION_SCOPE_OWNER(cpy)user"
        const val INSTALLATION_WORKSPACE_USR = "$INSTALLATION_SCOPE_OWNER(cpy)workspace"
        const val INSTALLATION_SCOPE_SWIFT_TYPE = "\$sSo010CodexAgentB17InstallationScopeCD"
        const val MCP_ENVIRONMENT_SOURCE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource"
        const val MCP_ENVIRONMENT_SOURCE_OWNER = "c:objc(cs)CodexAgentAgentMcpEnvironmentSource"
        const val MCP_ENVIRONMENT_LOCAL_USR = "$MCP_ENVIRONMENT_SOURCE_OWNER(cpy)local"
        const val MCP_ENVIRONMENT_REMOTE_USR = "$MCP_ENVIRONMENT_SOURCE_OWNER(cpy)remote"
        const val MCP_ENVIRONMENT_SOURCE_SWIFT_TYPE = "\$sSo010CodexAgentB20McpEnvironmentSourceCD"
        const val AUTHORIZATION_URL_OWNER = "c:objc(cs)CodexAgentCodexAuthorizationUrl"
        const val AUTHORIZATION_URL_COMPANION_OWNER =
            "c:objc(cs)CodexAgentCodexAuthorizationUrlCompanion"
        const val AUTHORIZATION_CHAT_GPT_USR = "$AUTHORIZATION_URL_COMPANION_OWNER(im)chatGptValue:"
        const val AUTHORIZATION_EXTERNAL_USR = "$AUTHORIZATION_URL_COMPANION_OWNER(im)externalValue:"
        const val AUTHORIZATION_PURPOSE_USR = "$AUTHORIZATION_URL_OWNER(py)purpose"
        const val D065_ENUM_USR = "c:objc(cs)CodexAgentAgentApprovalPreset(cpy)never"
        const val D065_CONSTRUCTOR_USR =
            "c:objc(cs)CodexAgentAgentFormOption(im)initWithValue:title:description:"
        const val D065_PROPERTY_USR = "c:objc(cs)CodexAgentAgentFormOption(py)description_"
        const val SWIFT_FAILURE_TEST =
            "CodexAgentObservationTests/testCodexOperationErrorsExposeStructuredFailure()"
        const val OBJECTIVE_C_FAILURE_TEST =
            "CodexAgentObservationTests/testObjectiveCConsumerExposesStructuredFailure()"
        val SHA_A = "a".repeat(64)
        val SHA_B = "b".repeat(64)
        val SHA_C = "c".repeat(64)
        val SHA_D = "d".repeat(64)
        val SHA_E = "e".repeat(64)
        val SHA_F = "f".repeat(64)
    }
}
