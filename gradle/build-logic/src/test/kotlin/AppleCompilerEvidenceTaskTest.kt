import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.work.DisableCachingByDefault

class AppleCompilerEvidenceTaskTest {
    @Test
    fun `commands bind exact module targets frameworks consumers and temporary outputs`() {
        val sdk = File("/tmp/apple evidence/SDK")
        val frameworks = File("/tmp/apple evidence/ios-arm64-simulator")
        val cache = File("/tmp/apple evidence/cache")
        val output = File("/tmp/apple evidence/output")
        val header = frameworks.resolve("CodexAgent.framework/Headers/CodexAgent.h")
        val swift = File("/tmp/apple evidence/CodexFailure.swift")
        val objectiveC = File("/tmp/apple evidence/CodexFailure.m")

        assertEquals(
            listOf(
                "/usr/bin/xcrun", "swift-symbolgraph-extract", "-module-name", "CodexAgent",
                "-target", "arm64-apple-ios15.0-simulator", "-sdk", sdk.absolutePath,
                "-F", frameworks.absolutePath, "-module-cache-path", cache.absolutePath,
                "-minimum-access-level", "public", "-skip-synthesized-members",
                "-output-dir", output.absolutePath,
            ),
            swiftSymbolGraphCommand(
                "arm64-apple-ios15.0-simulator", sdk, frameworks, cache, output,
            ),
        )
        assertEquals(
            listOf(
                "/usr/bin/xcrun", "clang", "-extract-api", "-x", "objective-c-header",
                "-target", "arm64-apple-ios15.0-simulator", "-isysroot", sdk.absolutePath,
                "-fmodules", "-fmodules-cache-path=${cache.absolutePath}", "-F", frameworks.absolutePath,
                header.absolutePath, "-o", output.absolutePath,
            ),
            objectiveCExtractApiCommand(
                "arm64-apple-ios15.0-simulator", sdk, frameworks, cache, header, output,
            ),
        )
        assertEquals(
            listOf(
                "/usr/bin/xcrun", "swiftc", "-typecheck", "-dump-ast", "-dump-ast-format", "json",
                "-target", "arm64-apple-ios15.0-simulator", "-sdk", sdk.absolutePath,
                "-F", frameworks.absolutePath, "-module-cache-path", cache.absolutePath, swift.absolutePath,
            ),
            swiftConsumerAstCommand(
                "arm64-apple-ios15.0-simulator", sdk, frameworks, cache, swift,
            ),
        )
        assertEquals(
            listOf(
                "/usr/bin/xcrun", "clang", "-fsyntax-only", "-x", "objective-c",
                "-target", "arm64-apple-ios15.0-simulator", "-isysroot", sdk.absolutePath,
                "-fmodules", "-fmodules-cache-path=${cache.absolutePath}", "-F", frameworks.absolutePath,
                "-Xclang", "-ast-dump=json", objectiveC.absolutePath,
            ),
            objectiveCConsumerAstCommand(
                "arm64-apple-ios15.0-simulator", sdk, frameworks, cache, objectiveC,
            ),
        )
        assertTrue(AppleCompilerEvidenceTask::class.java.isAnnotationPresent(DisableCachingByDefault::class.java))
    }

    @Test
    fun `canonical selection derives exactly 556 complete Apple binding capabilities`() {
        val keys = listOf(
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
            canonicalProperty("value", "kotlin/String!!", owner = "Other"),
        )
        val expected = keys.take(16) +
            appleCompilerFixtureD065Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
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
            appleCompilerFixtureD086Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD087Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD088Capabilities.map(AppleOrdinaryCapability::canonicalKey) +
            appleCompilerFixtureD089Capabilities.map(AppleOrdinaryCapability::canonicalKey)
        assertEquals(expected.sorted(), appleBindingCapabilityKeys(expected + keys.last()))
        assertFailsWith<IllegalStateException> { appleBindingCapabilityKeys(expected.drop(1)) }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(keys + canonicalProperty("future", "kotlin/String!!"))
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(keys + canonicalConstructor().replace("kotlin.Boolean", "kotlin.Int"))
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                it.replace("|kind=constructor|", "|kind=unsupported|")
            })
        }
        listOf(
            canonicalConstructor().replace("kotlin.Boolean", "kotlin.Int"),
            canonicalConstructor().replace("default=false", "default=true"),
            canonicalConstructor().replace("suspend=false", "suspend=true"),
            canonicalConstructor().replace("return=$CANONICAL_OWNER", "return=kotlin/String!!"),
            canonicalConstructor().replace("$CANONICAL_OWNER.<init>", "$CANONICAL_OWNER.changed"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(listOf(replacement) + expected.drop(1))
            }
        }
        listOf(
            canonicalProperty("code", "kotlin/String?"),
            canonicalProperty("code", "kotlin/String!!").replace("propertyKind=VAL", "propertyKind=VAR"),
            canonicalProperty("code", "kotlin/String!!").replace(".code|{}code[0]", ".changed|{}code[0]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(listOf(keys[0], replacement) + expected.drop(2))
            }
        }
        listOf(
            canonicalApprovalDecision("ACCEPT").replace(".ACCEPT", ".FUTURE"),
            canonicalApprovalDecision("ACCEPT").replace("|kind=enum-entry|", "|kind=property|"),
            canonicalApprovalDecision("ACCEPT").replace("null[0]", "null[1]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[4]) replacement else it })
            }
        }
        listOf(
            canonicalCollaborationMode("DEFAULT").replace(".DEFAULT", ".FUTURE"),
            canonicalCollaborationMode("DEFAULT").replace("|kind=enum-entry|", "|kind=property|"),
            canonicalCollaborationMode("DEFAULT").replace("null[0]", "null[1]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[6]) replacement else it })
            }
        }
        listOf(
            canonicalMessageRole("USER").replace(".USER", ".FUTURE"),
            canonicalMessageRole("USER").replace("|kind=enum-entry|", "|kind=property|"),
            canonicalMessageRole("USER").replace("null[0]", "null[1]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[8]) replacement else it })
            }
        }
        listOf(
            canonicalInstallationScope("User").replace(".User", ".Future"),
            canonicalInstallationScope("User").replace("|kind=enum-entry|", "|kind=property|"),
            canonicalInstallationScope("User").replace("null[0]", "null[1]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[10]) replacement else it })
            }
        }
        listOf(
            canonicalMcpEnvironmentSource("LOCAL").replace(".LOCAL", ".FUTURE"),
            canonicalMcpEnvironmentSource("LOCAL").replace("|kind=enum-entry|", "|kind=property|"),
            canonicalMcpEnvironmentSource("LOCAL").replace("null[0]", "null[1]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[12]) replacement else it })
            }
        }
        listOf(
            canonicalConversationIdConstructor().replace("kotlin.String", "kotlin.Int"),
            canonicalConversationIdConstructor().replace("default=false", "default=true"),
            canonicalConversationIdConstructor().replace("suspend=false", "suspend=true"),
            canonicalConversationIdConstructor().replace(
                "return=$CONVERSATION_ID_CANONICAL_OWNER",
                "return=kotlin/String!!",
            ),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[14]) replacement else it })
            }
        }
        listOf(
            canonicalProperty("value", "kotlin/String?", owner = "ConversationId"),
            canonicalProperty("value", "kotlin/String!!", owner = "ConversationId")
                .replace("propertyKind=VAL", "propertyKind=VAR"),
            canonicalProperty("value", "kotlin/String!!", owner = "ConversationId")
                .replace(".value|{}value[0]", ".changed|{}value[0]"),
        ).forEach { replacement ->
            assertFailsWith<IllegalStateException> {
                appleBindingCapabilityKeys(expected.map { if (it == keys[15]) replacement else it })
            }
        }
        val d076Factory = appleCompilerFixtureD076Capabilities.single {
            "Companion.chatGpt|" in it.canonicalKey
        }.canonicalKey
        val d076Purpose = appleCompilerFixtureD076Capabilities.single {
            "/CodexAuthorizationUrl.purpose|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d076Factory) it.replace("suspend=false", "suspend=true") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d076Purpose) it.replace("propertyKind=VAL", "propertyKind=VAR") else it
            })
        }
        val d077Constructor = appleCompilerFixtureD077Capabilities.single {
            "/AgentMcpServer|kind=constructor|" in it.canonicalKey
        }.canonicalKey
        val d077Property = appleCompilerFixtureD077Capabilities.single {
            "/AgentIntegration.McpServer.displayName|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d077Constructor) it.replace("default=true", "default=false") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d077Property) it.replace("kotlin/String!!", "kotlin/String?") else it
            })
        }
        val d078Constructor = appleCompilerFixtureD078Capabilities.single {
            "/AgentMcpTransport.Http|kind=constructor|" in it.canonicalKey
        }.canonicalKey
        val d078MapProperty = appleCompilerFixtureD078Capabilities.single {
            "/AgentElicitationResponse.content|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d078Constructor) it.replace("default=true", "default=false") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d078MapProperty) it.replace("AgentFormValue!!", "AgentFormValue?") else it
            })
        }
        val d079Constructor = appleCompilerFixtureD079Capabilities.single {
            "/AgentMessage|kind=constructor|" in it.canonicalKey
        }.canonicalKey
        val d079SetProperty = appleCompilerFixtureD079Capabilities.single {
            "/AgentTurnRequest.capabilities|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d079Constructor) it.replace("default=true", "default=false") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d079SetProperty) it.replace("AgentCapability!!", "AgentCapability?") else it
            })
        }
        val d080Constructor = appleCompilerFixtureD080Capabilities.single {
            "/AgentAuthenticationState|kind=constructor|" in it.canonicalKey
        }.canonicalKey
        val d080SetProperty = appleCompilerFixtureD080Capabilities.single {
            "/AgentInteractionState.resolvingRequestIds|" in it.canonicalKey
        }.canonicalKey
        val d080Method = appleCompilerFixtureD080Capabilities.single {
            "/AgentInteractionState.pendingFor|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d080Constructor) it.replaceFirst("default=true", "default=false") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d080SetProperty) it.replace("kotlin/String!!", "kotlin/String?") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d080Method) it.replace("return=kotlin.collections/List", "return=kotlin.collections/Set")
                else it
            })
        }
        val d081Object = appleCompilerFixtureD081Capabilities.single {
            "/AgentHookHandler.Agent|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d081Object) it.replace("|kind=object|", "|kind=property|") else it
            })
        }
        val d082Accepts = appleCompilerFixtureD082Capabilities.single {
            "/AgentFormField.accepts|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d082Accepts) it.replace("suspend=false", "suspend=true") else it
            })
        }
        val d083ConversationId = appleCompilerFixtureD083Capabilities.single {
            "/AgentPendingInteraction.conversationId|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d083ConversationId) it.replace("ConversationId!!", "ConversationId?") else it
            })
        }
        val d084HostStart = appleCompilerFixtureD084Capabilities.single {
            "/CodexHost.start|" in it.canonicalKey
        }.canonicalKey
        val d084FailedWorkspace = appleCompilerFixtureD084Capabilities.single {
            "/CodexHostState.Failed.workspace|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d084HostStart) it.replace("suspend=true", "suspend=false") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d084FailedWorkspace) it.replace("CodexWorkspace?", "CodexWorkspace!!") else it
            })
        }
        val d085Workspace = appleCompilerFixtureD085Capabilities.single {
            "/CodexAgent.workspace|" in it.canonicalKey
        }.canonicalKey
        val d085Availability = appleCompilerFixtureD085Capabilities.single {
            "/CodexSkills.isAvailable|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d085Workspace) it.replace("CodexWorkspace!!", "CodexWorkspace?") else it
            })
        }
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d085Availability) it.replace("kotlin/Boolean!!", "kotlin/String!!") else it
            })
        }
        val d086NullableTier = appleCompilerFixtureD086Capabilities.single {
            "/CodexModels.resolveServiceTier|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d086NullableTier) it.replace("AgentServiceTier?", "AgentServiceTier!!") else it
            })
        }
        val d087Authorize = appleCompilerFixtureD087Capabilities.single {
            "/CodexIntegrationAuthorization.authorize|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d087Authorize) it.replace("AgentIntegration>", "AgentPendingInteraction>") else it
            })
        }
        val d088Open = appleCompilerFixtureD088Capabilities.single {
            "/CodexConversations.open|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d088Open) it.replace("ConversationId?", "ConversationId!!") else it
            })
        }
        val d089Active = appleCompilerFixtureD089Capabilities.single {
            "/CodexIntegrationAuthorization.active|" in it.canonicalKey
        }.canonicalKey
        assertFailsWith<IllegalStateException> {
            appleBindingCapabilityKeys(expected.map {
                if (it == d089Active) it.replace("AgentIntegration?", "AgentIntegration!!") else it
            })
        }
    }

    @Test
    fun `real compiler shapes normalize to one exact 556-member contract per language`() {
        assertEquals(
            "c:objc(cs)CodexAgentAgentApprovalPreset",
            appleCompilerFixtureMemberOwnerUsr("c:objc(cs)CodexAgentAgentApprovalPreset(cpy)never"),
        )
        assertEquals(
            "c:objc(pl)CodexAgentAgentPendingInteraction",
            appleCompilerFixtureMemberOwnerUsr(
                "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId",
            ),
        )
        listOf(
            "c:objc(cs)Owner(cm)future(py)value",
            "c:objc(cs)(py)value",
            "c:objc(cs)Owner(py)",
            "c:objc(cs)Owner(cm)value",
            "c:objc(pl)OtherProtocol(py)value",
        ).forEach { malformed ->
            assertFailsWith<IllegalStateException> { appleCompilerFixtureMemberOwnerUsr(malformed) }
        }
        val swift = parseSwiftAppleBindingSurface(swiftSurfaceJson())
        val objectiveC = parseObjectiveCAppleBindingSurface(objectiveCSurfaceJson())
        assertEquals(671, swift.size)
        assertEquals(671, objectiveC.size)
        assertEquals(swift.map(AppleCompilerSymbol::precise), objectiveC.map(AppleCompilerSymbol::precise))
        assertEquals("swift.init", swift.single { it.precise == CONSTRUCTOR }.kind)
        assertEquals("objective-c.method", objectiveC.single { it.precise == CONSTRUCTOR }.kind)
        assertEquals("swift.init", swift.single { it.precise == CONVERSATION_ID_CONSTRUCTOR }.kind)
        assertEquals("objective-c.method", objectiveC.single { it.precise == CONVERSATION_ID_CONSTRUCTOR }.kind)
        assertTrue(swift.none { it.path.first() == "CDXFailure" })
        assertTrue(objectiveC.none { it.path.first() == "CDXFailure" })

        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson().replace("swift.init", "swift.method"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst("readonly", "readwrite"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(objectiveCSurfaceJson(includeMessageRelationship = false))
        }
        val d065EnumUsr = appleCompilerFixtureD065Capabilities.single {
            "/AgentApprovalPreset.NEVER|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d065EnumUsr))
        }
        val d065ConstructorUsr = appleCompilerFixtureD065Capabilities.single {
            "/AgentFormOption.<init>|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d065ConstructorUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replace("\"title\": \"accept\"", "\"title\": \"approve\""),
            )
        }
        val d076FactoryUsr = appleCompilerFixtureD076Capabilities.single {
            "Companion.chatGpt|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d076FactoryUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d076FactoryUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst("func chatGpt(value: String)", "func chatGpt(value: String?)"),
            )
        }
        val d077ConstructorUsr = appleCompilerFixtureD077Capabilities.single {
            "/AgentMcpServer.<init>|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d077ConstructorUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d077ConstructorUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "var configuration: AgentMcpServerConfiguration? { get }",
                    "var configuration: AgentMcpServerConfiguration { get }",
                ),
            )
        }
        val d078ContentUsr = appleCompilerFixtureD078Capabilities.single {
            "/AgentElicitationResponse.content|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d078ContentUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d078ContentUsr),
            )
        }
        val swiftSurface = swiftSurfaceJson()
        listOf(
            listOf("c:objc(pl)CodexAgentAgentFormValue"),
            listOf("s:SS", "s:SS", "c:objc(pl)CodexAgentAgentFormValue"),
            listOf("c:objc(pl)CodexAgentAgentFormValue", "s:SS"),
        ).forEach { identifiers ->
            val changed = swiftSurfaceJson(d078ContentTypeIdentifiers = identifiers)
            assertNotEquals(swiftSurface, changed)
            assertFailsWith<IllegalStateException> {
                parseSwiftAppleBindingSurface(changed)
            }
        }
        val d079CapabilitiesUsr = appleCompilerFixtureD079Capabilities.single {
            "/AgentMessage.capabilities|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d079CapabilitiesUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d079CapabilitiesUsr),
            )
        }
        listOf(
            listOf("s:Sh"),
            listOf("c:objc(cs)CodexAgentAgentCapability"),
            listOf("c:objc(cs)CodexAgentAgentCapability", "s:Sh"),
        ).forEach { identifiers ->
            val changed = swiftSurfaceJson(d079CapabilitiesTypeIdentifiers = identifiers)
            assertNotEquals(swiftSurface, changed)
            assertFailsWith<IllegalStateException> { parseSwiftAppleBindingSurface(changed) }
        }
        val d080MethodUsr = appleCompilerFixtureD080Capabilities.single {
            "/AgentInteractionState.pendingFor|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d080MethodUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d080MethodUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "func pendingFor(conversationId: ConversationId) -> [any AgentPendingInteraction]",
                    "func pendingFor(conversationId: ConversationId) -> [String]",
                ),
            )
        }
        val d081SharedUsr = appleCompilerFixtureD081Capabilities.single {
            "/AgentHookHandler.Agent|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d081SharedUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d081SharedUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "class var shared: AgentHookHandlerAgent { get }",
                    "class var shared: AgentHookHandlerPrompt { get }",
                ),
            )
        }
        val d082ValidateUsr = appleCompilerFixtureD082Capabilities.single {
            "/AgentElicitation.validate|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d082ValidateUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d082ValidateUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "func validate(content: [String : any AgentFormValue]) -> AgentElicitationValidation",
                    "func validate(content: [String : any AgentFormValue]) -> Bool",
                ),
            )
        }
        val d083ConversationIdUsr = appleCompilerFixtureD083Capabilities.single {
            "/AgentPendingInteraction.conversationId|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d083ConversationIdUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson(wrongD083RelationshipKind = d083ConversationIdUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD083RelationshipKind = d083ConversationIdUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d083ConversationIdUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "protocol AgentPendingInteraction",
                    "class AgentPendingInteraction",
                ),
            )
        }
        val classRelationshipDrift = swiftSurfaceJson().replaceFirst(
            "\"kind\": \"memberOf\",\n            \"source\": \"$d082ValidateUsr\"",
            "\"kind\": \"requirementOf\",\n            \"source\": \"$d082ValidateUsr\"",
        )
        assertNotEquals(swiftSurfaceJson(), classRelationshipDrift)
        assertFailsWith<IllegalStateException> { parseSwiftAppleBindingSurface(classRelationshipDrift) }
        val d084StartUsr = appleCompilerFixtureD084Capabilities.single {
            "/CodexHost.start|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD084Callback = d084StartUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(wrongD084CallbackLanguage = d084StartUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "func start(completionHandler: @escaping @Sendable ((any Error)?) -> Void)",
                    "func start(completionHandler: @escaping @Sendable ((String)?) -> Void)",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD084CallbackRelationship = d084StartUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst("func start() async throws", "func start() async"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst(
                    "startWithCompletionHandler:(void (^)(NSError *))",
                    "startWithCompletionHandler:(void (^)(NSString *))",
                ),
            )
        }
        val d087AuthenticateUsr = appleCompilerFixtureD087Capabilities.single {
            "/CodexAuthentication.authenticate|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD084Callback = d087AuthenticateUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "func authenticate(method: any CodexAuthenticationMethod) async throws",
                    "func authenticate() async throws",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst(
                    "@property (readonly) id<CodexAgentKotlinx_coroutines_coreStateFlow> isAuthenticated;",
                    "@property (readonly) NSString * isAuthenticated;",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst(
                    "c:Qoobjc(pl)CodexAgentCodexAuthenticationMethod",
                    "c:objc(pl)CodexAgentCodexAuthenticationMethod",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst(
                    "c:Qoobjc(pl)CodexAgentAgentIntegration",
                    "c:objc(pl)CodexAgentAgentIntegration",
                ),
            )
        }
        val d088OpenUsr = appleCompilerFixtureD088Capabilities.single {
            "/CodexConversations.open|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD084Callback = d088OpenUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "func open(conversationId: ConversationId?, settings: AgentConversationSettings) " +
                        "async throws -> CodexConversation",
                    "func open(conversationId: ConversationId, settings: AgentConversationSettings) " +
                        "async throws -> CodexConversation",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst(
                    "@property (readonly) id<CodexAgentKotlinx_coroutines_coreStateFlow> currentMessages;",
                    "@property (readonly) NSArray * currentMessages;",
                ),
            )
        }
        val d089IsAuthorizingUsr = appleCompilerFixtureD089Capabilities.single {
            "/CodexIntegrationAuthorization.isAuthorizing|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson(d089StateFlowTypeDrift = d089IsAuthorizingUsr),
            )
        }
        val d089AuthorizationStateUsr = appleCompilerFixtureD089Capabilities.single {
            "/CodexIntegrationAuthorization.state|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson(missingD065Relationship = d089AuthorizationStateUsr),
            )
        }
        val d089ApprovalsUsr = appleCompilerFixtureD089Capabilities.single {
            "/CodexInteractions.approvals|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(d089StateFlowTypeDrift = d089ApprovalsUsr),
            )
        }
        val d085SkillsAvailabilityUsr = appleCompilerFixtureD085Capabilities.single {
            "/CodexSkills.isAvailable|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD065Relationship = d085SkillsAvailabilityUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson(wrongD065Relationship = d085SkillsAvailabilityUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "var authentication: CodexAuthentication { get }",
                    "var authentication: CodexConnectors { get }",
                ),
            )
        }
        val d086ResolveTierUsr = appleCompilerFixtureD086Capabilities.single {
            "/CodexModels.resolveServiceTier|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(swiftSurfaceJson(missingD084Callback = d086ResolveTierUsr))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson(wrongD084CallbackLanguage = d086ResolveTierUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson(missingD084CallbackRelationship = d086ResolveTierUsr),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replaceFirst(
                    "func resolveServiceTier(model: AgentModel, resolution: AgentResolution) async throws -> " +
                        "AgentServiceTier?",
                    "func resolveServiceTier(model: AgentModel, resolution: AgentResolution) async throws -> " +
                        "AgentModel?",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingSurface(
                objectiveCSurfaceJson().replaceFirst(
                    "completionHandler:(void (^)(CodexAgentAgentServiceTier *, NSError *))",
                    "completionHandler:(void (^)(CodexAgentAgentModel *, NSError *))",
                ),
            )
        }
    }

    @Test
    fun `compiled AST references bind 556 exact USRs and reject drift`() {
        val swift = parseSwiftAppleBindingReferences(swiftReferencesJson())
        val objectiveC = parseObjectiveCAppleBindingReferences(objectiveCReferencesJson())
        assertEquals(556, swift.size)
        assertEquals(556, objectiveC.size)
        assertEquals(swift.map(AppleCompilerReference::precise), objectiveC.map(AppleCompilerReference::precise))
        assertEquals(556, swift.map(AppleCompilerReference::precise).distinct().size)

        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(py)message", "(py)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(objectiveCReferencesJson().replace("\"BOOL\"", "\"int\""))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replace("CodexAgentCodexFailure *", "CDXFailure *"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(py)value", "(py)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst("CodexAgentConversationId *", "CDXConversationId *"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(cpy)remote", "(cpy)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentMcpEnvironmentSource * _Nonnull",
                    "CodexAgentAgentMcpEnvironmentSource *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace("(py)content", "(py)removed"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "initWithAction:content:", "removed:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(cpy)workspace", "(cpy)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentInstallationScope * _Nonnull",
                    "CodexAgentAgentInstallationScope *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(objectiveCReferencesJson().replaceFirst("true", "false"))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replaceFirst(
                    "\$syySo010CodexAgentA20AuthenticationMethod_p_tYaKcSo0abaC0CcD",
                    "\$syyyYaKcSo010CodexAgentA14AuthenticationCcD",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "authenticateMethod:completionHandler:", "authenticateWithCompletionHandler:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(cpy)decline", "(cpy)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(objectiveCReferencesJson().replace("\"decline\"", "\"removed\""))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentApprovalDecision * _Nonnull",
                    "CodexAgentAgentApprovalDecision *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(cpy)plan", "(cpy)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(objectiveCReferencesJson().replace("\"plan\"", "\"removed\""))
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(swiftReferencesJson().replace("(cpy)assistant", "(cpy)removed"))
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentMessageRole * _Nonnull",
                    "CodexAgentAgentMessageRole *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace("(im)chatGptValue:", "(im)removed:"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst("chatGptValue:", "removedValue:"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentCodexAuthorizationUrlCompanion *",
                    "CodexAgentCodexAuthorizationUrl *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace("(py)purpose", "(py)removed"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "(im)initWithName:displayName:authStatus:configuration:origin:canRemove:",
                    "(im)removed:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "\$sySo010CodexAgentB9McpServerCSS_SSSo0abbC10AuthStatusCSo0abbcD13ConfigurationCSg" +
                        "So0abB14ResourceOriginCSbtcABmcD",
                    "\$sSSD",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "initWithName:displayName:authStatus:configuration:origin:canRemove:",
                    "removed:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentMcpServer *",
                    "CodexAgentAgentMcpServerConfiguration *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "(im)initWithId:clientMessageId:role:text:collaborationMode:reasoning:plan:" +
                        "shellCommand:exitCode:capabilities:invocations:",
                    "(im)removed:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "initWithPrompt:clientMessageId:model:effort:serviceTier:approvalPreset:" +
                        "capabilities:invocations:collaborationMode:",
                    "removed:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "\$sySbSo010CodexAgentB18PendingInteraction_p_tcSo0abbD5StateCcD",
                    "\$sSbD",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "id<CodexAgentAgentPendingInteraction> _Nonnull",
                    "id<CodexAgentAgentPendingInteraction>",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "\$sSo010CodexAgentb11HookHandlerB0CD",
                    "\$sSo010CodexAgentB17HookHandlerPromptCD",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentHookHandlerAgent * _Nonnull",
                    "CodexAgentAgentHookHandlerAgent *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "\$sySbSo010CodexAgentB9FormValue_pSg_tcSo0abbC5FieldCcD",
                    "\$sSbD",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentAgentElicitationResponseCompanion *",
                    "CodexAgentAgentElicitation *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replace(
                    "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId",
                    "c:objc(pl)CodexAgentAgentPendingInteraction(py)removed",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "id<CodexAgentAgentInvocation>",
                    "id<CodexAgentAgentPendingInteraction>",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replaceFirst("(im)startWithCompletionHandler:", "(im)removed:"),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "selectWorkspaceSelection:completionHandler:",
                    "removed:completionHandler:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "id<CodexAgentCodexPlatform>",
                    "id<CodexAgentCodexPlatform> _Nonnull",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replaceFirst(
                    "c:objc(cs)CodexAgentCodexAgent(py)workspace",
                    "c:objc(cs)CodexAgentCodexAgent(py)removed",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "CodexAgentCodexSkills *",
                    "CodexAgentCodexPlugins *",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replaceFirst(
                    "c:objc(cs)CodexAgentCodexModels(im)resolveServiceTierModel:resolution:completionHandler:",
                    "c:objc(cs)CodexAgentCodexModels(im)removed:",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "void (^)(CodexAgentAgentServiceTier *, NSError *)",
                    "void (^)(CodexAgentAgentModel *, NSError *)",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson().replaceFirst(
                    "\$sySo010CodexAgentA12ConversationCSo0abC2IdCSg_So0abbC8SettingsCtYaKcSo0abA13ConversationsCcD",
                    "\$sySo010CodexAgentA12ConversationCSo0abC2IdC_So0abbC8SettingsCtYaKcSo0abA13ConversationsCcD",
                ),
            )
        }
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson().replaceFirst(
                    "runShellCommandCommand:completionHandler:",
                    "runShellCommand:completionHandler:",
                ),
            )
        }
        val d089ElicitationsUsr = appleCompilerFixtureD089Capabilities.single {
            "/CodexInteractions.elicitations|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingReferences(
                swiftReferencesJson(d089ValueTypeDrift = d089ElicitationsUsr),
            )
        }
        val d089InteractionStateUsr = appleCompilerFixtureD089Capabilities.single {
            "/CodexInteractions.state|" in it.canonicalKey
        }.usr
        assertFailsWith<IllegalStateException> {
            parseObjectiveCAppleBindingReferences(
                objectiveCReferencesJson(d089ReceiverDrift = d089InteractionStateUsr),
            )
        }
    }

    @Test
    fun `normalization digest is deterministic and semantic drift changes it`() {
        val first = JsonArray(parseSwiftAppleBindingSurface(swiftSurfaceJson()).map { JsonPrimitive(it.precise) })
        val same = JsonArray(parseSwiftAppleBindingSurface(swiftSurfaceJson()).map { JsonPrimitive(it.precise) })
        val drift = JsonArray(first + JsonPrimitive("c:objc(cs)Foreign"))
        assertEquals(appleCompilerJsonDigest(first), appleCompilerJsonDigest(same))
        assertNotEquals(appleCompilerJsonDigest(first), appleCompilerJsonDigest(drift))
    }

    private fun canonicalConstructor(): String =
        "common|owner=$CANONICAL_OWNER|kind=constructor|abi=$CANONICAL_OWNER.<init>|" +
            "<init>(kotlin.String;kotlin.String;kotlin.Boolean){}[0]|return=$CANONICAL_OWNER|suspend=false|" +
            "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false," +
            "REGULAR:kotlin/String!!:default=false:vararg=false," +
            "REGULAR:kotlin/Boolean!!:default=false:vararg=false]"

    private fun canonicalConversationIdConstructor(): String =
        "common|owner=$CONVERSATION_ID_CANONICAL_OWNER|kind=constructor|" +
            "abi=$CONVERSATION_ID_CANONICAL_OWNER.<init>|<init>(kotlin.String){}[0]|" +
            "return=$CONVERSATION_ID_CANONICAL_OWNER|suspend=false|" +
            "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]"

    private fun canonicalProperty(name: String, type: String, owner: String = "CodexFailure"): String {
        val canonicalOwner = "io.github.codex_agent_labs.codexagent.agent/$owner"
        return "common|owner=$canonicalOwner|kind=property|abi=$canonicalOwner.$name|{}$name[0]|" +
            "propertyKind=VAL|type=$type"
    }

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

    private fun swiftSurfaceJson(
        includeMessageRelationship: Boolean = true,
        missingD065Relationship: String? = null,
        wrongD065Relationship: String? = null,
        wrongD083RelationshipKind: String? = null,
        missingD084Callback: String? = null,
        wrongD084CallbackLanguage: String? = null,
        missingD084CallbackRelationship: String? = null,
        d078ContentTypeIdentifiers: List<String>? = null,
        d079CapabilitiesTypeIdentifiers: List<String>? = null,
        d089StateFlowTypeDrift: String? = null,
    ): String = surfaceJson(
        language = "swift",
        symbols = listOf(
            symbol(
                OWNER, "swift", "swift.class", listOf("CodexFailure"), "CodexFailure", "public",
                fragments(keyword("class"), text(" "), identifier("CodexFailure")),
            ),
            symbol(
                CONSTRUCTOR, "swift", "swift.init", listOf("CodexFailure", "init(code:message:isRecoverable:)"),
                "init(code:message:isRecoverable:)", "public",
                fragments(
                    keyword("init"), text("("), external("code"), text(": "), type("String", "s:SS"),
                    text(", "), external("message"), text(": "), type("String", "s:SS"), text(", "),
                    external("isRecoverable"), text(": "), type("Bool", "s:Sb"), text(")"),
                ),
                listOf(
                    parameter("code", fragments(identifier("code"), text(": "), type("String", "s:SS"))),
                    parameter("message", fragments(identifier("message"), text(": "), type("String", "s:SS"))),
                    parameter("isRecoverable", fragments(identifier("isRecoverable"), text(": "), type("Bool", "s:Sb"))),
                ),
            ),
            swiftProperty(CODE, "code", "String", "s:SS"),
            swiftProperty(RECOVERABLE, "isRecoverable", "Bool", "s:Sb"),
            swiftProperty(MESSAGE, "message", "String", "s:SS"),
            symbol(
                CONVERSATION_ID_OWNER, "swift", "swift.class", listOf("ConversationId"),
                "ConversationId", "public",
                fragments(keyword("class"), text(" "), identifier("ConversationId")),
            ),
            symbol(
                CONVERSATION_ID_CONSTRUCTOR, "swift", "swift.init",
                listOf("ConversationId", "init(value:)"), "init(value:)", "public",
                fragments(
                    keyword("init"), text("("), external("value"), text(": "),
                    type("String", "s:SS"), text(")"),
                ),
                listOf(parameter("value", fragments(identifier("value"), text(": "), type("String", "s:SS")))),
            ),
            symbol(
                CONVERSATION_ID_VALUE, "swift", "swift.property", listOf("ConversationId", "value"),
                "value", "open",
                fragments(
                    keyword("var"), text(" "), identifier("value"), text(": "), type("String", "s:SS"),
                    text(" { "), keyword("get"), text(" }"),
                ),
            ),
            symbol(
                APPROVAL_OWNER, "swift", "swift.class", listOf("AgentApprovalDecision"),
                "AgentApprovalDecision", "public",
                fragments(keyword("class"), text(" "), identifier("AgentApprovalDecision")),
            ),
            swiftTypeProperty(ACCEPT, "accept", "AgentApprovalDecision", APPROVAL_OWNER),
            swiftTypeProperty(DECLINE, "decline", "AgentApprovalDecision", APPROVAL_OWNER),
            symbol(
                COLLABORATION_OWNER, "swift", "swift.class", listOf("AgentCollaborationMode"),
                "AgentCollaborationMode", "public",
                fragments(keyword("class"), text(" "), identifier("AgentCollaborationMode")),
            ),
            swiftTypeProperty(DEFAULT, "default_", "AgentCollaborationMode", COLLABORATION_OWNER),
            swiftTypeProperty(PLAN, "plan", "AgentCollaborationMode", COLLABORATION_OWNER),
            symbol(
                MESSAGE_ROLE_OWNER, "swift", "swift.class", listOf("AgentMessageRole"),
                "AgentMessageRole", "public",
                fragments(keyword("class"), text(" "), identifier("AgentMessageRole")),
            ),
            swiftTypeProperty(USER, "user", "AgentMessageRole", MESSAGE_ROLE_OWNER),
            swiftTypeProperty(ASSISTANT, "assistant", "AgentMessageRole", MESSAGE_ROLE_OWNER),
            symbol(
                INSTALLATION_SCOPE_OWNER, "swift", "swift.class", listOf("AgentInstallationScope"),
                "AgentInstallationScope", "public",
                fragments(keyword("class"), text(" "), identifier("AgentInstallationScope")),
            ),
            swiftTypeProperty(
                INSTALLATION_USER, "user", "AgentInstallationScope", INSTALLATION_SCOPE_OWNER,
            ),
            swiftTypeProperty(
                INSTALLATION_WORKSPACE, "workspace", "AgentInstallationScope", INSTALLATION_SCOPE_OWNER,
            ),
            symbol(
                MCP_ENVIRONMENT_SOURCE_OWNER, "swift", "swift.class", listOf("AgentMcpEnvironmentSource"),
                "AgentMcpEnvironmentSource", "public",
                fragments(keyword("class"), text(" "), identifier("AgentMcpEnvironmentSource")),
            ),
            swiftTypeProperty(
                MCP_ENVIRONMENT_LOCAL, "local", "AgentMcpEnvironmentSource", MCP_ENVIRONMENT_SOURCE_OWNER,
            ),
            swiftTypeProperty(
                MCP_ENVIRONMENT_REMOTE, "remote", "AgentMcpEnvironmentSource", MCP_ENVIRONMENT_SOURCE_OWNER,
            ),
        ) + appleCompilerFixtureD065SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD073SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD074SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD075SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD076SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD077SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD078SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(
                precise,
                "swift",
                if (precise == "c:objc(cs)CodexAgentAgentElicitationResponse(py)content" &&
                    d078ContentTypeIdentifiers != null
                ) {
                    expected.copy(typeIdentifiers = d078ContentTypeIdentifiers)
                } else {
                    expected
                },
            )
        } + appleCompilerFixtureD079SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(
                precise,
                "swift",
                if (precise == "c:objc(cs)CodexAgentAgentMessage(py)capabilities" &&
                    d079CapabilitiesTypeIdentifiers != null
                ) {
                    expected.copy(typeIdentifiers = d079CapabilitiesTypeIdentifiers)
                } else {
                    expected
                },
            )
        } + appleCompilerFixtureD080SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD081SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD082SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(
                precise, "swift", expected,
                omitEmptyParameters = expected.parameters.isEmpty() && expected.returns != null,
            )
        } + appleCompilerFixtureD083SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD084SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD084SwiftCallbackSymbols()
            .filterKeys { it != missingD084Callback }
            .map { (precise, expected) ->
                expectedRawSymbol(
                    precise,
                    if (precise == wrongD084CallbackLanguage) "objective-c" else "swift",
                    expected,
                )
        } + appleCompilerFixtureD085SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD086SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD086SwiftCallbackSymbols()
            .filterKeys { it != missingD084Callback }
            .map { (precise, expected) ->
                expectedRawSymbol(
                    precise,
                    if (precise == wrongD084CallbackLanguage) "objective-c" else "swift",
                    expected,
                )
        } + appleCompilerFixtureD087SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD087SwiftCallbackSymbols()
            .filterKeys { it != missingD084Callback }
            .map { (precise, expected) ->
                expectedRawSymbol(
                    precise,
                    if (precise == wrongD084CallbackLanguage) "objective-c" else "swift",
                    expected,
                )
        } + appleCompilerFixtureD088SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "swift", expected)
        } + appleCompilerFixtureD088SwiftCallbackSymbols()
            .filterKeys { it != missingD084Callback }
            .map { (precise, expected) ->
                expectedRawSymbol(
                    precise,
                    if (precise == wrongD084CallbackLanguage) "objective-c" else "swift",
                    expected,
                )
        } + appleCompilerFixtureD089SwiftSymbols().map { (precise, expected) ->
            expectedRawSymbol(
                precise,
                "swift",
                if (precise == d089StateFlowTypeDrift) {
                    expected.copy(typeIdentifiers = listOf("c:objc(pl)CodexAgentCodexAuthenticationMethod"))
                } else {
                    expected
                },
            )
        },
        includeMessageRelationship = includeMessageRelationship,
        missingD065Relationship = missingD065Relationship,
        wrongD065Relationship = wrongD065Relationship,
        wrongD083RelationshipKind = wrongD083RelationshipKind,
        missingD084CallbackRelationship = missingD084CallbackRelationship,
    )

    private fun objectiveCSurfaceJson(
        includeMessageRelationship: Boolean = true,
        missingD065Relationship: String? = null,
        wrongD065Relationship: String? = null,
        wrongD083RelationshipKind: String? = null,
        d089StateFlowTypeDrift: String? = null,
    ): String = surfaceJson(
        language = "objective-c",
        symbols = listOf(
            symbol(
                OWNER, "objective-c", "objective-c.class", listOf("CodexAgentCodexFailure"),
                "CodexAgentCodexFailure", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentCodexFailure"), text(" : "),
                    type("CodexAgentBase", "c:objc(cs)CodexAgentBase"),
                ),
            ),
            symbol(
                CONSTRUCTOR, "objective-c", "objective-c.method",
                listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
                "initWithCode:message:isRecoverable:", "public",
                fragments(
                    text("- ("), keyword("instancetype"), text(") "), identifier("initWithCode:"), text("("),
                    type("NSString", "c:objc(cs)NSString"), text(" *) "), internal("code"), text(" "),
                    identifier("message:"), text("("), type("NSString", "c:objc(cs)NSString"), text(" *) "),
                    internal("message"), text(" "), identifier("isRecoverable:"), text("("),
                    type("BOOL", "c:@T@BOOL"), text(") "), internal("isRecoverable"), text(";"),
                ),
                listOf(
                    parameter("code", fragments(text("("), type("NSString", "c:objc(cs)NSString"), text(" *) "), internal("code"))),
                    parameter("message", fragments(text("("), type("NSString", "c:objc(cs)NSString"), text(" *) "), internal("message"))),
                    parameter("isRecoverable", fragments(text("("), type("BOOL", "c:@T@BOOL"), text(") "), internal("isRecoverable"))),
                ),
                fragments(keyword("instancetype")),
            ),
            objectiveCProperty(CODE, "code", "NSString", "c:objc(cs)NSString", pointer = true),
            objectiveCProperty(RECOVERABLE, "isRecoverable", "BOOL", "c:@T@BOOL", pointer = false),
            objectiveCProperty(MESSAGE, "message", "NSString", "c:objc(cs)NSString", pointer = true),
            symbol(
                CONVERSATION_ID_OWNER, "objective-c", "objective-c.class",
                listOf("CodexAgentConversationId"), "CodexAgentConversationId", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentConversationId"), text(" : "),
                    type("CodexAgentBase", "c:objc(cs)CodexAgentBase"),
                ),
            ),
            symbol(
                CONVERSATION_ID_CONSTRUCTOR, "objective-c", "objective-c.method",
                listOf("CodexAgentConversationId", "initWithValue:"), "initWithValue:", "public",
                fragments(
                    text("- ("), keyword("instancetype"), text(") "), identifier("initWithValue:"), text("("),
                    type("NSString", "c:objc(cs)NSString"), text(" *) "), internal("value"), text(";"),
                ),
                listOf(
                    parameter(
                        "value",
                        fragments(text("("), type("NSString", "c:objc(cs)NSString"), text(" *) "), internal("value")),
                    ),
                ),
                fragments(keyword("instancetype")),
            ),
            symbol(
                CONVERSATION_ID_VALUE, "objective-c", "objective-c.property",
                listOf("CodexAgentConversationId", "value"), "value", "public",
                fragments(
                    keyword("@property"), text(" ("), keyword("readonly"), text(") "),
                    type("NSString", "c:objc(cs)NSString"), text(" * "), identifier("value"), text(";"),
                ),
            ),
            symbol(
                APPROVAL_OWNER, "objective-c", "objective-c.class", listOf("CodexAgentAgentApprovalDecision"),
                "CodexAgentAgentApprovalDecision", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentAgentApprovalDecision"), text(" : "),
                    type("CodexAgentKotlinEnum", "c:objc(cs)CodexAgentKotlinEnum"),
                ),
            ),
            objectiveCTypeProperty(ACCEPT, "accept", "AgentApprovalDecision", APPROVAL_OWNER),
            objectiveCTypeProperty(DECLINE, "decline", "AgentApprovalDecision", APPROVAL_OWNER),
            symbol(
                COLLABORATION_OWNER, "objective-c", "objective-c.class",
                listOf("CodexAgentAgentCollaborationMode"), "CodexAgentAgentCollaborationMode", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentAgentCollaborationMode"), text(" : "),
                    type("CodexAgentKotlinEnum", "c:objc(cs)CodexAgentKotlinEnum"),
                ),
            ),
            objectiveCTypeProperty(DEFAULT, "default_", "AgentCollaborationMode", COLLABORATION_OWNER),
            objectiveCTypeProperty(PLAN, "plan", "AgentCollaborationMode", COLLABORATION_OWNER),
            symbol(
                MESSAGE_ROLE_OWNER, "objective-c", "objective-c.class",
                listOf("CodexAgentAgentMessageRole"), "CodexAgentAgentMessageRole", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentAgentMessageRole"), text(" : "),
                    type("CodexAgentKotlinEnum", "c:objc(cs)CodexAgentKotlinEnum"),
                ),
            ),
            objectiveCTypeProperty(USER, "user", "AgentMessageRole", MESSAGE_ROLE_OWNER),
            objectiveCTypeProperty(ASSISTANT, "assistant", "AgentMessageRole", MESSAGE_ROLE_OWNER),
            symbol(
                INSTALLATION_SCOPE_OWNER, "objective-c", "objective-c.class",
                listOf("CodexAgentAgentInstallationScope"), "CodexAgentAgentInstallationScope", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentAgentInstallationScope"), text(" : "),
                    type("CodexAgentKotlinEnum", "c:objc(cs)CodexAgentKotlinEnum"),
                ),
            ),
            objectiveCTypeProperty(
                INSTALLATION_USER, "user", "AgentInstallationScope", INSTALLATION_SCOPE_OWNER,
            ),
            objectiveCTypeProperty(
                INSTALLATION_WORKSPACE, "workspace", "AgentInstallationScope", INSTALLATION_SCOPE_OWNER,
            ),
            symbol(
                MCP_ENVIRONMENT_SOURCE_OWNER, "objective-c", "objective-c.class",
                listOf("CodexAgentAgentMcpEnvironmentSource"), "CodexAgentAgentMcpEnvironmentSource", "public",
                fragments(
                    keyword("@interface"), text(" "), identifier("CodexAgentAgentMcpEnvironmentSource"), text(" : "),
                    type("CodexAgentKotlinEnum", "c:objc(cs)CodexAgentKotlinEnum"),
                ),
            ),
            objectiveCTypeProperty(
                MCP_ENVIRONMENT_LOCAL, "local", "AgentMcpEnvironmentSource", MCP_ENVIRONMENT_SOURCE_OWNER,
            ),
            objectiveCTypeProperty(
                MCP_ENVIRONMENT_REMOTE, "remote", "AgentMcpEnvironmentSource", MCP_ENVIRONMENT_SOURCE_OWNER,
            ),
        ) + appleCompilerFixtureD065ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD073ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD074ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD075ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD076ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD077ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD078ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD079ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD080ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD081ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD082ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD083ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD084ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD085ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD086ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD087ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD088ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(precise, "objective-c", expected)
        } + appleCompilerFixtureD089ObjectiveCSymbols().map { (precise, expected) ->
            expectedRawSymbol(
                precise,
                "objective-c",
                if (precise == d089StateFlowTypeDrift) {
                    expected.copy(
                        typeIdentifiers =
                            listOf("c:objc(pl)CodexAgentKotlinx_coroutines_coreStateFlow"),
                    )
                } else {
                    expected
                },
            )
        },
        includeMessageRelationship = includeMessageRelationship,
        missingD065Relationship = missingD065Relationship,
        wrongD065Relationship = wrongD065Relationship,
        wrongD083RelationshipKind = wrongD083RelationshipKind,
        missingD084CallbackRelationship = null,
    )

    private fun surfaceJson(
        language: String,
        symbols: List<JsonObject>,
        includeMessageRelationship: Boolean,
        missingD065Relationship: String?,
        wrongD065Relationship: String?,
        wrongD083RelationshipKind: String?,
        missingD084CallbackRelationship: String?,
    ): String = releaseJson.encodeToString(JsonElement.serializer(), buildJsonObject {
        put("symbols", JsonArray(symbols + buildJsonObject {
            put("identifier", buildJsonObject {
                put("precise", JsonPrimitive("c:objc(cs)CDXFailure"))
                put("interfaceLanguage", JsonPrimitive(language))
            })
        }))
        put("relationships", buildJsonArray {
            listOf(CONSTRUCTOR, CODE, RECOVERABLE).forEach { add(relationship(it)) }
            if (includeMessageRelationship) add(relationship(MESSAGE))
            listOf(CONVERSATION_ID_CONSTRUCTOR, CONVERSATION_ID_VALUE).forEach {
                add(relationship(it, CONVERSATION_ID_OWNER))
            }
            listOf(ACCEPT, DECLINE).forEach { add(relationship(it, APPROVAL_OWNER)) }
            listOf(DEFAULT, PLAN).forEach { add(relationship(it, COLLABORATION_OWNER)) }
            listOf(USER, ASSISTANT).forEach { add(relationship(it, MESSAGE_ROLE_OWNER)) }
            listOf(INSTALLATION_USER, INSTALLATION_WORKSPACE).forEach {
                add(relationship(it, INSTALLATION_SCOPE_OWNER))
            }
            listOf(MCP_ENVIRONMENT_LOCAL, MCP_ENVIRONMENT_REMOTE).forEach {
                add(relationship(it, MCP_ENVIRONMENT_SOURCE_OWNER))
            }
            val d065Symbols = if (language == "swift") {
                appleCompilerFixtureD065SwiftSymbols()
            } else {
                appleCompilerFixtureD065ObjectiveCSymbols()
            }
            d065Symbols.filterValues { it.path.size > 1 }.keys.forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d073Symbols = if (language == "swift") {
                appleCompilerFixtureD073SwiftSymbols()
            } else {
                appleCompilerFixtureD073ObjectiveCSymbols()
            }
            d073Symbols.filterValues { it.path.size > 1 }.keys.forEach { precise ->
                add(relationship(precise, appleOwnerUsr(precise)))
            }
            val d074Symbols = if (language == "swift") {
                appleCompilerFixtureD074SwiftSymbols()
            } else {
                appleCompilerFixtureD074ObjectiveCSymbols()
            }
            d074Symbols.filterValues { it.path.size > 1 }.keys.forEach { precise ->
                add(relationship(precise, appleOwnerUsr(precise)))
            }
            val d075Symbols = if (language == "swift") {
                appleCompilerFixtureD075SwiftSymbols()
            } else {
                appleCompilerFixtureD075ObjectiveCSymbols()
            }
            d075Symbols.filterValues { it.path.size > 1 }.keys.forEach { precise ->
                add(relationship(precise, appleOwnerUsr(precise)))
            }
            val d076Symbols = if (language == "swift") {
                appleCompilerFixtureD076SwiftSymbols()
            } else {
                appleCompilerFixtureD076ObjectiveCSymbols()
            }
            val d076MemberUsrs = appleCompilerFixtureD076Capabilities.mapTo(mutableSetOf()) { it.usr }
            d076Symbols.keys.filter(d076MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d077Symbols = if (language == "swift") {
                appleCompilerFixtureD077SwiftSymbols()
            } else {
                appleCompilerFixtureD077ObjectiveCSymbols()
            }
            val d077MemberUsrs = appleCompilerFixtureD077Capabilities.mapTo(mutableSetOf()) { it.usr }
            d077Symbols.keys.filter(d077MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d078Symbols = if (language == "swift") {
                appleCompilerFixtureD078SwiftSymbols()
            } else {
                appleCompilerFixtureD078ObjectiveCSymbols()
            }
            val d078MemberUsrs = appleCompilerFixtureD078Capabilities.mapTo(mutableSetOf()) { it.usr }
            d078Symbols.keys.filter(d078MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d079Symbols = if (language == "swift") {
                appleCompilerFixtureD079SwiftSymbols()
            } else {
                appleCompilerFixtureD079ObjectiveCSymbols()
            }
            val d079MemberUsrs = appleCompilerFixtureD079Capabilities.mapTo(mutableSetOf()) { it.usr }
            d079Symbols.keys.filter(d079MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d080Symbols = if (language == "swift") {
                appleCompilerFixtureD080SwiftSymbols()
            } else {
                appleCompilerFixtureD080ObjectiveCSymbols()
            }
            val d080MemberUsrs = appleCompilerFixtureD080Capabilities.mapTo(mutableSetOf()) { it.usr }
            d080Symbols.keys.filter(d080MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d081Symbols = if (language == "swift") {
                appleCompilerFixtureD081SwiftSymbols()
            } else {
                appleCompilerFixtureD081ObjectiveCSymbols()
            }
            val d081MemberUsrs = appleCompilerFixtureD081Capabilities.mapTo(mutableSetOf()) { it.usr }
            d081Symbols.keys.filter(d081MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d082Symbols = if (language == "swift") {
                appleCompilerFixtureD082SwiftSymbols()
            } else {
                appleCompilerFixtureD082ObjectiveCSymbols()
            }
            val d082MemberUsrs = appleCompilerFixtureD082Capabilities.mapTo(mutableSetOf()) { it.usr }
            d082Symbols.keys.filter(d082MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d083Symbols = if (language == "swift") {
                appleCompilerFixtureD083SwiftSymbols()
            } else {
                appleCompilerFixtureD083ObjectiveCSymbols()
            }
            val d083MemberUsrs = appleCompilerFixtureD083Capabilities.mapTo(mutableSetOf()) { it.usr }
            d083Symbols.keys.filter(d083MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    val expectedKind = if (language == "swift") "requirementOf" else "memberOf"
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                        if (precise == wrongD083RelationshipKind) {
                            if (expectedKind == "requirementOf") "memberOf" else "requirementOf"
                        } else {
                            expectedKind
                        },
                    ))
                }
            }
            val d084Symbols = if (language == "swift") {
                appleCompilerFixtureD084SwiftSymbols()
            } else {
                appleCompilerFixtureD084ObjectiveCSymbols()
            }
            val d084MemberUsrs = appleCompilerFixtureD084Capabilities.mapTo(mutableSetOf()) { it.usr }
            d084Symbols.keys.filter(d084MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                    if (language == "swift" &&
                        precise in appleCompilerFixtureD084SwiftCallbackSymbols() &&
                        precise != missingD084CallbackRelationship
                    ) {
                        add(relationship(precise, appleOwnerUsr(precise)))
                    }
                }
            }
            val d085Symbols = if (language == "swift") {
                appleCompilerFixtureD085SwiftSymbols()
            } else {
                appleCompilerFixtureD085ObjectiveCSymbols()
            }
            val d085MemberUsrs = appleCompilerFixtureD085Capabilities.mapTo(mutableSetOf()) { it.usr }
            d085Symbols.keys.filter(d085MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
            val d086Symbols = if (language == "swift") {
                appleCompilerFixtureD086SwiftSymbols()
            } else {
                appleCompilerFixtureD086ObjectiveCSymbols()
            }
            val d086MemberUsrs = appleCompilerFixtureD086Capabilities.mapTo(mutableSetOf()) { it.usr }
            d086Symbols.keys.filter(d086MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                    if (language == "swift" && precise != missingD084CallbackRelationship) {
                        add(relationship(precise, appleOwnerUsr(precise)))
                    }
                }
            }
            val d087Symbols = if (language == "swift") {
                appleCompilerFixtureD087SwiftSymbols()
            } else {
                appleCompilerFixtureD087ObjectiveCSymbols()
            }
            val d087MemberUsrs = appleCompilerFixtureD087Capabilities.mapTo(mutableSetOf()) { it.usr }
            d087Symbols.keys.filter(d087MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                    if (language == "swift" &&
                        precise in appleCompilerFixtureD087SwiftCallbackSymbols() &&
                        precise != missingD084CallbackRelationship
                    ) {
                        add(relationship(precise, appleOwnerUsr(precise)))
                    }
                }
            }
            val d088Symbols = if (language == "swift") {
                appleCompilerFixtureD088SwiftSymbols()
            } else {
                appleCompilerFixtureD088ObjectiveCSymbols()
            }
            val d088MemberUsrs = appleCompilerFixtureD088Capabilities.mapTo(mutableSetOf()) { it.usr }
            d088Symbols.keys.filter(d088MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                    if (language == "swift" &&
                        precise in appleCompilerFixtureD088SwiftCallbackSymbols() &&
                        precise != missingD084CallbackRelationship
                    ) {
                        add(relationship(precise, appleOwnerUsr(precise)))
                    }
                }
            }
            val d089Symbols = if (language == "swift") {
                appleCompilerFixtureD089SwiftSymbols()
            } else {
                appleCompilerFixtureD089ObjectiveCSymbols()
            }
            val d089MemberUsrs = appleCompilerFixtureD089Capabilities.mapTo(mutableSetOf()) { it.usr }
            d089Symbols.keys.filter(d089MemberUsrs::contains).forEach { precise ->
                if (precise != missingD065Relationship) {
                    add(relationship(
                        precise,
                        if (precise == wrongD065Relationship) OWNER else appleOwnerUsr(precise),
                    ))
                }
            }
        })
    })

    private fun expectedRawSymbol(
        precise: String,
        language: String,
        expected: ExpectedAppleCompilerSymbol,
        omitEmptyParameters: Boolean = false,
    ) = symbol(
        precise,
        language,
        expected.kind,
        expected.path,
        expected.title,
        expected.access,
        fragments(
            text(expected.declaration),
            *expected.typeIdentifiers.map { type("", it) }.toTypedArray(),
        ),
        expected.parameters.map { (name, declaration) -> parameter(name, fragments(text(declaration))) },
        expected.returns?.let { fragments(text(it)) },
        omitEmptyParameters,
    )

    private fun appleOwnerUsr(memberUsr: String): String =
        listOf("(cpy)", "(py)", "(im)").fold(memberUsr) { owner, marker -> owner.substringBefore(marker) }

    private fun symbol(
        precise: String,
        language: String,
        kind: String,
        path: List<String>,
        title: String,
        access: String,
        declaration: JsonArray,
        parameters: List<JsonObject> = emptyList(),
        returns: JsonArray? = null,
        omitEmptyParameters: Boolean = false,
    ) = buildJsonObject {
        put("identifier", buildJsonObject {
            put("precise", JsonPrimitive(precise)); put("interfaceLanguage", JsonPrimitive(language))
        })
        put("kind", buildJsonObject { put("identifier", JsonPrimitive(kind)) })
        put("pathComponents", buildJsonArray { path.forEach { add(JsonPrimitive(it)) } })
        put("names", buildJsonObject { put("title", JsonPrimitive(title)) })
        put("accessLevel", JsonPrimitive(access)); put("declarationFragments", declaration)
        if (parameters.isNotEmpty() || returns != null) put("functionSignature", buildJsonObject {
            if (!omitEmptyParameters || parameters.isNotEmpty()) put("parameters", JsonArray(parameters))
            returns?.let { put("returns", it) }
        })
    }

    private fun swiftProperty(precise: String, name: String, typeName: String, typeUsr: String) = symbol(
        precise, "swift", "swift.property", listOf("CodexFailure", name), name, "open",
        fragments(
            keyword("var"), text(" "), identifier(name), text(": "), type(typeName, typeUsr),
            text(" { "), keyword("get"), text(" }"),
        ),
    )

    private fun swiftTypeProperty(precise: String, name: String, typeName: String, owner: String) = symbol(
        precise, "swift", "swift.type.property", listOf(typeName, name), name, "open",
        fragments(
            keyword("class"), text(" "), keyword("var"), text(" "), identifier(name), text(": "),
            type(typeName, owner), text(" { "), keyword("get"), text(" }"),
        ),
    )

    private fun objectiveCProperty(
        precise: String,
        name: String,
        typeName: String,
        typeUsr: String,
        pointer: Boolean,
    ) = symbol(
        precise, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", name), name, "public",
        fragments(
            keyword("@property"), text(" ("), keyword("readonly"), text(") "), type(typeName, typeUsr),
            text(if (pointer) " * " else " "), identifier(name), text(";"),
        ),
    )

    private fun objectiveCTypeProperty(precise: String, name: String, typeName: String, owner: String) = symbol(
        precise, "objective-c", "objective-c.type.property",
        listOf("CodexAgent$typeName", name), name, "public",
        fragments(
            keyword("@property"), text(" ("), keyword("class"), text(", "), keyword("readonly"), text(") "),
            type("CodexAgent$typeName", owner), text(" * "), identifier(name), text(";"),
        ),
    )

    private fun relationship(source: String, target: String = OWNER, kind: String = "memberOf") = buildJsonObject {
        put("kind", JsonPrimitive(kind)); put("source", JsonPrimitive(source)); put("target", JsonPrimitive(target))
    }

    private fun parameter(name: String, fragments: JsonArray) = buildJsonObject {
        put("name", JsonPrimitive(name)); put("declarationFragments", fragments)
    }

    private fun fragments(vararg values: JsonObject) = JsonArray(values.toList())
    private fun keyword(value: String) = fragment("keyword", value)
    private fun text(value: String) = fragment("text", value)
    private fun identifier(value: String) = fragment("identifier", value)
    private fun external(value: String) = fragment("externalParam", value)
    private fun internal(value: String) = fragment("internalParam", value)
    private fun type(value: String, precise: String) = fragment("typeIdentifier", value, precise)
    private fun fragment(kind: String, spelling: String, precise: String? = null) = buildJsonObject {
        put("kind", JsonPrimitive(kind)); put("spelling", JsonPrimitive(spelling))
        precise?.let { put("preciseIdentifier", JsonPrimitive(it)) }
    }

    private fun swiftReferencesJson(d089ValueTypeDrift: String? = null): String = releaseJson.encodeToString(
        JsonElement.serializer(),
        buildJsonObject { put("inner", buildJsonArray {
            add(swiftReference("declref_expr", "init", CONSTRUCTOR, FAILURE_SWIFT_CONSTRUCTOR_TYPE))
            add(swiftReference("declref_expr", "init", CONSTRUCTOR, FAILURE_SWIFT_CONSTRUCTOR_TYPE))
            add(swiftReference("member_ref_expr", "code", CODE, "\$sSSD"))
            add(swiftReference("member_ref_expr", "isRecoverable", RECOVERABLE, "\$sSbD"))
            add(swiftReference("member_ref_expr", "message", MESSAGE, "\$sSSD"))
            add(swiftReference(
                "declref_expr", "init", CONVERSATION_ID_CONSTRUCTOR, CONVERSATION_ID_SWIFT_CONSTRUCTOR_TYPE,
            ))
            add(swiftReference("member_ref_expr", "value", CONVERSATION_ID_VALUE, "\$sSSD"))
            add(swiftReference("member_ref_expr", "accept", ACCEPT, APPROVAL_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "decline", DECLINE, APPROVAL_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "default_", DEFAULT, COLLABORATION_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "plan", PLAN, COLLABORATION_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "user", USER, MESSAGE_ROLE_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "assistant", ASSISTANT, MESSAGE_ROLE_SWIFT_TYPE))
            add(swiftReference(
                "member_ref_expr", "user", INSTALLATION_USER, INSTALLATION_SCOPE_SWIFT_TYPE,
            ))
            add(swiftReference(
                "member_ref_expr", "workspace", INSTALLATION_WORKSPACE, INSTALLATION_SCOPE_SWIFT_TYPE,
            ))
            add(swiftReference(
                "member_ref_expr", "local", MCP_ENVIRONMENT_LOCAL, MCP_ENVIRONMENT_SOURCE_SWIFT_TYPE,
            ))
            add(swiftReference(
                "member_ref_expr", "remote", MCP_ENVIRONMENT_REMOTE, MCP_ENVIRONMENT_SOURCE_SWIFT_TYPE,
            ))
            val ordinaryUsrs =
                (appleCompilerFixtureD065Capabilities + appleCompilerFixtureD073Capabilities +
                    appleCompilerFixtureD074Capabilities + appleCompilerFixtureD075Capabilities +
                    appleCompilerFixtureD076Capabilities + appleCompilerFixtureD077Capabilities +
                    appleCompilerFixtureD078Capabilities + appleCompilerFixtureD079Capabilities +
                    appleCompilerFixtureD080Capabilities + appleCompilerFixtureD081Capabilities +
                    appleCompilerFixtureD082Capabilities + appleCompilerFixtureD083Capabilities +
                    appleCompilerFixtureD084Capabilities + appleCompilerFixtureD085Capabilities +
                    appleCompilerFixtureD086Capabilities + appleCompilerFixtureD087Capabilities +
                    appleCompilerFixtureD088Capabilities + appleCompilerFixtureD089Capabilities)
                    .mapTo(mutableSetOf(), AppleOrdinaryCapability::usr)
            appleCompilerFixtureSwiftReferences().filter { it.precise in ordinaryUsrs }.forEach { reference ->
                add(swiftReference(
                    reference.kind,
                    reference.name,
                    reference.precise,
                    if (reference.precise == d089ValueTypeDrift) "\$sSSD" else reference.valueType,
                ))
            }
        }) },
    )

    private fun swiftReference(kind: String, name: String, precise: String, type: String) = buildJsonObject {
        put("_kind", JsonPrimitive(kind)); put("type", JsonPrimitive(type))
        put("decl", buildJsonObject {
            put("base_name", JsonPrimitive(name)); put("decl_usr", JsonPrimitive(precise))
        })
    }

    private fun objectiveCReferencesJson(d089ReceiverDrift: String? = null): String = releaseJson.encodeToString(
        JsonElement.serializer(),
        buildJsonObject { put("inner", buildJsonArray {
            add(buildJsonObject {
                put("kind", JsonPrimitive("ObjCMessageExpr"))
                put("selector", JsonPrimitive("initWithCode:message:isRecoverable:"))
                put("type", qualifiedType("CodexAgentCodexFailure *"))
                put("inner", buildJsonArray {
                    add(buildJsonObject { put("classType", qualifiedType("CodexAgentCodexFailure")) })
                    add(buildJsonObject { put("type", qualifiedType("NSString *")) })
                    add(buildJsonObject { put("type", qualifiedType("NSString *")) })
                    add(buildJsonObject { put("type", qualifiedType("BOOL")) })
                })
            })
            add(objectiveCPropertyReference("code"))
            add(objectiveCPropertyReference("code"))
            add(objectiveCPropertyReference("isRecoverable"))
            add(objectiveCPropertyReference("message"))
            add(buildJsonObject {
                put("kind", JsonPrimitive("ObjCMessageExpr"))
                put("selector", JsonPrimitive("initWithValue:"))
                put("type", qualifiedType("CodexAgentConversationId *"))
                put("inner", buildJsonArray {
                    add(buildJsonObject { put("classType", qualifiedType("CodexAgentConversationId")) })
                    add(buildJsonObject { put("type", qualifiedType("NSString *")) })
                })
            })
            add(objectiveCConversationIdValueReference())
            add(objectiveCDecisionReference("accept"))
            add(objectiveCDecisionReference("decline"))
            add(objectiveCCollaborationReference("default_"))
            add(objectiveCCollaborationReference("plan"))
            add(objectiveCMessageRoleReference("user"))
            add(objectiveCMessageRoleReference("assistant"))
            add(objectiveCInstallationScopeReference("user"))
            add(objectiveCInstallationScopeReference("workspace"))
            add(objectiveCMcpEnvironmentSourceReference("local"))
            add(objectiveCMcpEnvironmentSourceReference("remote"))
            val ordinaryUsrs =
                (appleCompilerFixtureD065Capabilities + appleCompilerFixtureD073Capabilities +
                    appleCompilerFixtureD074Capabilities + appleCompilerFixtureD075Capabilities +
                    appleCompilerFixtureD076Capabilities + appleCompilerFixtureD077Capabilities +
                    appleCompilerFixtureD078Capabilities + appleCompilerFixtureD079Capabilities +
                    appleCompilerFixtureD080Capabilities + appleCompilerFixtureD081Capabilities +
                    appleCompilerFixtureD082Capabilities + appleCompilerFixtureD083Capabilities +
                    appleCompilerFixtureD084Capabilities + appleCompilerFixtureD085Capabilities +
                    appleCompilerFixtureD086Capabilities + appleCompilerFixtureD087Capabilities +
                    appleCompilerFixtureD088Capabilities + appleCompilerFixtureD089Capabilities)
                    .mapTo(mutableSetOf(), AppleOrdinaryCapability::usr)
            appleCompilerFixtureObjectiveCReferences().filter { it.precise in ordinaryUsrs }.forEach { reference ->
                add(objectiveCReference(
                    if (reference.precise == d089ReceiverDrift) {
                        reference.copy(receiverType = "CodexAgentCodexAuthentication *")
                    } else {
                        reference
                    },
                ))
            }
        }) },
    )

    private fun objectiveCReference(reference: AppleCompilerReference) = when (reference.kind) {
        "ObjCMessageExpr" -> buildJsonObject {
            put("kind", JsonPrimitive(reference.kind))
            put("selector", JsonPrimitive(reference.name))
            put("type", qualifiedType(reference.valueType))
            val finiteInstanceUsrs = (appleCompilerFixtureD082Capabilities +
                appleCompilerFixtureD084Capabilities.filter { "|kind=function|" in it.canonicalKey } +
                appleCompilerFixtureD086Capabilities +
                appleCompilerFixtureD087Capabilities.filter { "|kind=function|" in it.canonicalKey } +
                appleCompilerFixtureD088Capabilities.filter { "|kind=function|" in it.canonicalKey })
                .mapTo(mutableSetOf()) { it.usr }
            if (reference.argumentTypes.isEmpty() && reference.precise !in finiteInstanceUsrs) {
                put("receiverKind", JsonPrimitive("class"))
                put("classType", qualifiedType(requireNotNull(reference.receiverType)))
            } else {
                put("inner", buildJsonArray {
                    add(buildJsonObject {
                        if (reference.precise in
                            (appleCompilerFixtureD076Capabilities + appleCompilerFixtureD080Capabilities.filter {
                                "|kind=function|" in it.canonicalKey
                            } + appleCompilerFixtureD082Capabilities +
                                appleCompilerFixtureD084Capabilities.filter {
                                    "|kind=function|" in it.canonicalKey
                                } + appleCompilerFixtureD086Capabilities +
                                appleCompilerFixtureD087Capabilities.filter {
                                    "|kind=function|" in it.canonicalKey
                                } + appleCompilerFixtureD088Capabilities.filter {
                                    "|kind=function|" in it.canonicalKey
                                }).map { capability -> capability.usr }
                        ) {
                            put("type", qualifiedType(requireNotNull(reference.receiverType)))
                        } else {
                            put("classType", qualifiedType(requireNotNull(reference.receiverType)))
                        }
                    })
                    reference.argumentTypes.forEach { add(buildJsonObject { put("type", qualifiedType(it)) }) }
                })
            }
        }
        "ObjCPropertyRefExpr" -> buildJsonObject {
            put("kind", JsonPrimitive(reference.kind))
            put("type", qualifiedType(reference.valueType))
            put("property", buildJsonObject { put("name", JsonPrimitive(reference.name)) })
            put("isMessagingGetter", JsonPrimitive(true))
            put("inner", buildJsonArray {
                add(buildJsonObject { put("type", qualifiedType(requireNotNull(reference.receiverType))) })
            })
        }
        else -> error("Unexpected Objective-C reference kind: ${reference.kind}")
    }

    private fun objectiveCPropertyReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCPropertyRefExpr")); put("type", qualifiedType("<pseudo-object type>"))
        put("property", buildJsonObject { put("name", JsonPrimitive(name)) })
        put("isMessagingGetter", JsonPrimitive(true))
        put("inner", buildJsonArray {
            add(buildJsonObject { put("type", qualifiedType("CodexAgentCodexFailure *")) })
        })
    }

    private fun objectiveCConversationIdValueReference() = buildJsonObject {
        put("kind", JsonPrimitive("ObjCPropertyRefExpr")); put("type", qualifiedType("<pseudo-object type>"))
        put("property", buildJsonObject { put("name", JsonPrimitive("value")) })
        put("isMessagingGetter", JsonPrimitive(true))
        put("inner", buildJsonArray {
            add(buildJsonObject { put("type", qualifiedType("CodexAgentConversationId *")) })
        })
    }

    private fun objectiveCDecisionReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentApprovalDecision * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentApprovalDecision"))
        put("inner", buildJsonArray {})
    }

    private fun objectiveCCollaborationReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentCollaborationMode * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentCollaborationMode"))
        put("inner", buildJsonArray {})
    }

    private fun objectiveCMessageRoleReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentMessageRole * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentMessageRole"))
        put("inner", buildJsonArray {})
    }

    private fun objectiveCInstallationScopeReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentInstallationScope * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentInstallationScope"))
        put("inner", buildJsonArray {})
    }

    private fun objectiveCMcpEnvironmentSourceReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentMcpEnvironmentSource * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentMcpEnvironmentSource"))
        put("inner", buildJsonArray {})
    }

    private fun qualifiedType(value: String) = buildJsonObject { put("qualType", JsonPrimitive(value)) }

    private companion object {
        const val CANONICAL_OWNER = "io.github.codex_agent_labs.codexagent.agent/CodexFailure"
        const val OWNER = "c:objc(cs)CodexAgentCodexFailure"
        const val CONSTRUCTOR = "$OWNER(im)initWithCode:message:isRecoverable:"
        const val FAILURE_SWIFT_CONSTRUCTOR_TYPE = "\$sySo010CodexAgentA7FailureCSS_SSSbtcABmcD"
        const val CODE = "$OWNER(py)code"
        const val RECOVERABLE = "$OWNER(py)isRecoverable"
        const val MESSAGE = "$OWNER(py)message"
        const val CONVERSATION_ID_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexagent.agent/ConversationId"
        const val CONVERSATION_ID_OWNER = "c:objc(cs)CodexAgentConversationId"
        const val CONVERSATION_ID_CONSTRUCTOR = "$CONVERSATION_ID_OWNER(im)initWithValue:"
        const val CONVERSATION_ID_VALUE = "$CONVERSATION_ID_OWNER(py)value"
        const val CONVERSATION_ID_SWIFT_CONSTRUCTOR_TYPE =
            "\$sySo24CodexAgentConversationIdCSS_tcABmcD"
        const val APPROVAL_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexagent.agent/AgentApprovalDecision"
        const val APPROVAL_OWNER = "c:objc(cs)CodexAgentAgentApprovalDecision"
        const val ACCEPT = "$APPROVAL_OWNER(cpy)accept"
        const val DECLINE = "$APPROVAL_OWNER(cpy)decline"
        const val APPROVAL_SWIFT_TYPE = "\$sSo010CodexAgentB16ApprovalDecisionCD"
        const val COLLABORATION_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexagent.agent/AgentCollaborationMode"
        const val COLLABORATION_OWNER = "c:objc(cs)CodexAgentAgentCollaborationMode"
        const val DEFAULT = "$COLLABORATION_OWNER(cpy)default_"
        const val PLAN = "$COLLABORATION_OWNER(cpy)plan"
        const val COLLABORATION_SWIFT_TYPE = "\$sSo010CodexAgentB17CollaborationModeCD"
        const val MESSAGE_ROLE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexagent.agent/AgentMessageRole"
        const val MESSAGE_ROLE_OWNER = "c:objc(cs)CodexAgentAgentMessageRole"
        const val USER = "$MESSAGE_ROLE_OWNER(cpy)user"
        const val ASSISTANT = "$MESSAGE_ROLE_OWNER(cpy)assistant"
        const val MESSAGE_ROLE_SWIFT_TYPE = "\$sSo010CodexAgentB11MessageRoleCD"
        const val INSTALLATION_SCOPE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexagent.agent/AgentInstallationScope"
        const val INSTALLATION_SCOPE_OWNER = "c:objc(cs)CodexAgentAgentInstallationScope"
        const val INSTALLATION_USER = "$INSTALLATION_SCOPE_OWNER(cpy)user"
        const val INSTALLATION_WORKSPACE = "$INSTALLATION_SCOPE_OWNER(cpy)workspace"
        const val INSTALLATION_SCOPE_SWIFT_TYPE = "\$sSo010CodexAgentB17InstallationScopeCD"
        const val MCP_ENVIRONMENT_SOURCE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexagent.agent/AgentMcpEnvironmentSource"
        const val MCP_ENVIRONMENT_SOURCE_OWNER = "c:objc(cs)CodexAgentAgentMcpEnvironmentSource"
        const val MCP_ENVIRONMENT_LOCAL = "$MCP_ENVIRONMENT_SOURCE_OWNER(cpy)local"
        const val MCP_ENVIRONMENT_REMOTE = "$MCP_ENVIRONMENT_SOURCE_OWNER(cpy)remote"
        const val MCP_ENVIRONMENT_SOURCE_SWIFT_TYPE = "\$sSo010CodexAgentB20McpEnvironmentSourceCD"
    }
}
