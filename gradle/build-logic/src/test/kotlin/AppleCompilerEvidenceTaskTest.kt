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
    fun `canonical selection derives exactly ten complete Apple binding capabilities`() {
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
            canonicalProperty("value", "kotlin/String!!", owner = "Other"),
        )
        val expected = keys.take(10)
        assertEquals(expected.sorted(), appleBindingCapabilityKeys(keys))
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
    }

    @Test
    fun `real compiler shapes normalize to one exact ten-member contract per language`() {
        val swift = parseSwiftAppleBindingSurface(swiftSurfaceJson())
        val objectiveC = parseObjectiveCAppleBindingSurface(objectiveCSurfaceJson())
        assertEquals(14, swift.size)
        assertEquals(14, objectiveC.size)
        assertEquals(swift.map(AppleCompilerSymbol::precise), objectiveC.map(AppleCompilerSymbol::precise))
        assertEquals("swift.init", swift.single { "initWithCode" in it.precise }.kind)
        assertEquals("objective-c.method", objectiveC.single { "initWithCode" in it.precise }.kind)
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
        assertFailsWith<IllegalStateException> {
            parseSwiftAppleBindingSurface(
                swiftSurfaceJson().replace("\"title\": \"accept\"", "\"title\": \"approve\""),
            )
        }
    }

    @Test
    fun `compiled AST references bind ten exact USRs and reject drift`() {
        val swift = parseSwiftAppleBindingReferences(swiftReferencesJson())
        val objectiveC = parseObjectiveCAppleBindingReferences(objectiveCReferencesJson())
        assertEquals(10, swift.size)
        assertEquals(10, objectiveC.size)
        assertEquals(swift.map(AppleCompilerReference::precise), objectiveC.map(AppleCompilerReference::precise))
        assertEquals(10, swift.map(AppleCompilerReference::precise).distinct().size)

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
            parseObjectiveCAppleBindingReferences(objectiveCReferencesJson().replaceFirst("true", "false"))
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

    private fun canonicalProperty(name: String, type: String, owner: String = "CodexFailure"): String {
        val canonicalOwner = "io.github.codex_agent_labs.codexmobile.agent/$owner"
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

    private fun swiftSurfaceJson(includeMessageRelationship: Boolean = true): String = surfaceJson(
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
        ),
        includeMessageRelationship = includeMessageRelationship,
    )

    private fun objectiveCSurfaceJson(includeMessageRelationship: Boolean = true): String = surfaceJson(
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
        ),
        includeMessageRelationship = includeMessageRelationship,
    )

    private fun surfaceJson(
        language: String,
        symbols: List<JsonObject>,
        includeMessageRelationship: Boolean,
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
            listOf(ACCEPT, DECLINE).forEach { add(relationship(it, APPROVAL_OWNER)) }
            listOf(DEFAULT, PLAN).forEach { add(relationship(it, COLLABORATION_OWNER)) }
            listOf(USER, ASSISTANT).forEach { add(relationship(it, MESSAGE_ROLE_OWNER)) }
        })
    })

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
    ) = buildJsonObject {
        put("identifier", buildJsonObject {
            put("precise", JsonPrimitive(precise)); put("interfaceLanguage", JsonPrimitive(language))
        })
        put("kind", buildJsonObject { put("identifier", JsonPrimitive(kind)) })
        put("pathComponents", buildJsonArray { path.forEach { add(JsonPrimitive(it)) } })
        put("names", buildJsonObject { put("title", JsonPrimitive(title)) })
        put("accessLevel", JsonPrimitive(access)); put("declarationFragments", declaration)
        if (parameters.isNotEmpty() || returns != null) put("functionSignature", buildJsonObject {
            put("parameters", JsonArray(parameters)); returns?.let { put("returns", it) }
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

    private fun relationship(source: String, target: String = OWNER) = buildJsonObject {
        put("kind", JsonPrimitive("memberOf")); put("source", JsonPrimitive(source)); put("target", JsonPrimitive(target))
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

    private fun swiftReferencesJson(): String = releaseJson.encodeToString(
        JsonElement.serializer(),
        buildJsonObject { put("inner", buildJsonArray {
            add(swiftReference("declref_expr", "init", CONSTRUCTOR, "constructor-type"))
            add(swiftReference("declref_expr", "init", CONSTRUCTOR, "constructor-type"))
            add(swiftReference("member_ref_expr", "code", CODE, "\$sSSD"))
            add(swiftReference("member_ref_expr", "isRecoverable", RECOVERABLE, "\$sSbD"))
            add(swiftReference("member_ref_expr", "message", MESSAGE, "\$sSSD"))
            add(swiftReference("member_ref_expr", "accept", ACCEPT, APPROVAL_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "decline", DECLINE, APPROVAL_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "default_", DEFAULT, COLLABORATION_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "plan", PLAN, COLLABORATION_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "user", USER, MESSAGE_ROLE_SWIFT_TYPE))
            add(swiftReference("member_ref_expr", "assistant", ASSISTANT, MESSAGE_ROLE_SWIFT_TYPE))
        }) },
    )

    private fun swiftReference(kind: String, name: String, precise: String, type: String) = buildJsonObject {
        put("_kind", JsonPrimitive(kind)); put("type", JsonPrimitive(type))
        put("decl", buildJsonObject {
            put("base_name", JsonPrimitive(name)); put("decl_usr", JsonPrimitive(precise))
        })
    }

    private fun objectiveCReferencesJson(): String = releaseJson.encodeToString(
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
            add(objectiveCDecisionReference("accept"))
            add(objectiveCDecisionReference("decline"))
            add(objectiveCCollaborationReference("default_"))
            add(objectiveCCollaborationReference("plan"))
            add(objectiveCMessageRoleReference("user"))
            add(objectiveCMessageRoleReference("assistant"))
        }) },
    )

    private fun objectiveCPropertyReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCPropertyRefExpr")); put("type", qualifiedType("<pseudo-object type>"))
        put("property", buildJsonObject { put("name", JsonPrimitive(name)) })
        put("isMessagingGetter", JsonPrimitive(true))
        put("inner", buildJsonArray {
            add(buildJsonObject { put("type", qualifiedType("CodexAgentCodexFailure *")) })
        })
    }

    private fun objectiveCDecisionReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentApprovalDecision * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentApprovalDecision"))
    }

    private fun objectiveCCollaborationReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentCollaborationMode * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentCollaborationMode"))
    }

    private fun objectiveCMessageRoleReference(name: String) = buildJsonObject {
        put("kind", JsonPrimitive("ObjCMessageExpr")); put("selector", JsonPrimitive(name))
        put("type", qualifiedType("CodexAgentAgentMessageRole * _Nonnull"))
        put("receiverKind", JsonPrimitive("class"))
        put("classType", qualifiedType("CodexAgentAgentMessageRole"))
    }

    private fun qualifiedType(value: String) = buildJsonObject { put("qualType", JsonPrimitive(value)) }

    private companion object {
        const val CANONICAL_OWNER = "io.github.codex_agent_labs.codexmobile.agent/CodexFailure"
        const val OWNER = "c:objc(cs)CodexAgentCodexFailure"
        const val CONSTRUCTOR = "$OWNER(im)initWithCode:message:isRecoverable:"
        const val CODE = "$OWNER(py)code"
        const val RECOVERABLE = "$OWNER(py)isRecoverable"
        const val MESSAGE = "$OWNER(py)message"
        const val APPROVAL_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision"
        const val APPROVAL_OWNER = "c:objc(cs)CodexAgentAgentApprovalDecision"
        const val ACCEPT = "$APPROVAL_OWNER(cpy)accept"
        const val DECLINE = "$APPROVAL_OWNER(cpy)decline"
        const val APPROVAL_SWIFT_TYPE = "\$sSo010CodexAgentB16ApprovalDecisionCD"
        const val COLLABORATION_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode"
        const val COLLABORATION_OWNER = "c:objc(cs)CodexAgentAgentCollaborationMode"
        const val DEFAULT = "$COLLABORATION_OWNER(cpy)default_"
        const val PLAN = "$COLLABORATION_OWNER(cpy)plan"
        const val COLLABORATION_SWIFT_TYPE = "\$sSo010CodexAgentB17CollaborationModeCD"
        const val MESSAGE_ROLE_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole"
        const val MESSAGE_ROLE_OWNER = "c:objc(cs)CodexAgentAgentMessageRole"
        const val USER = "$MESSAGE_ROLE_OWNER(cpy)user"
        const val ASSISTANT = "$MESSAGE_ROLE_OWNER(cpy)assistant"
        const val MESSAGE_ROLE_SWIFT_TYPE = "\$sSo010CodexAgentB11MessageRoleCD"
    }
}
