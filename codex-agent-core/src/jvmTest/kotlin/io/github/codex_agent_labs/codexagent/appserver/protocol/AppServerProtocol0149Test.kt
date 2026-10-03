package io.github.codex_agent_labs.codexagent.appserver.protocol

import io.github.codex_agent_labs.codexagent.appserver.protocol.generated.*
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlinx.serialization.json.Json

class AppServerProtocol0149Test {
    private val json = Json { explicitNulls = false }

    @Test
    fun decodesBedrockAccountSetupAndDiscovery() {
        val login = json.decodeFromString(
            AppServerClientMethods.AccountLoginStart.paramsSerializer,
            """{"type":"amazonBedrock","apiKey":"secret","region":"eu-west-1"}""",
        )
        assertEquals("eu-west-1", assertIs<LoginAccountParamsAmazonBedrock>(login).region)

        val account = json.decodeFromString(
            AppServerClientMethods.AccountRead.responseSerializer,
            """{"requiresOpenaiAuth":false,"account":{"type":"amazonBedrock","usesCodexManagedCredentials":true}}""",
        ).account
        assertEquals(true, assertIs<AccountAmazonBedrockAccount>(account).usesCodexManagedCredentials)
    }

    @Test
    fun decodesProjectAndStrictReviewNotifications() {
        val project = json.decodeFromString(
            ServerNotification.serializer(),
            """{"method":"project/changed","params":{"changeType":"updated","projectId":"project-1"}}""",
        )
        assertEquals(
            "project-1",
            assertIs<ServerNotificationProjectChangedNotification>(project).params.projectId,
        )

        val threadProject = json.decodeFromString(
            ServerNotification.serializer(),
            """{"method":"thread/project/updated","params":{"threadId":"thread-1","projectId":"project-1"}}""",
        )
        assertEquals(
            "project-1",
            assertIs<ServerNotificationThreadProjectUpdatedNotification>(threadProject).params.projectId,
        )

        val strictReview = json.decodeFromString(
            ServerNotification.serializer(),
            """{"method":"autoApprovalReview/strictReviewRequired","params":{"threadId":"thread-1","turnId":"turn-1","startedAtMs":42}}""",
        )
        assertEquals(
            42,
            assertIs<ServerNotificationAutoApprovalReviewStrictReviewRequiredNotification>(strictReview)
                .params.startedAtMs,
        )
    }

    @Test
    fun optional0149FieldsDecodeBothNewAndLegacyPayloads() {
        val asyncItem = json.decodeFromString(
            ThreadItem.serializer(),
            """{"type":"agentMessage","id":"item-1","text":"hello","delivery":"async"}""",
        )
        assertEquals(AgentMessageDelivery.ASYNC, assertIs<ThreadItemAgentMessageThreadItem>(asyncItem).delivery)
        val legacyItem = json.decodeFromString(
            ThreadItem.serializer(),
            """{"type":"agentMessage","id":"item-2","text":"hello"}""",
        )
        assertNull(assertIs<ThreadItemAgentMessageThreadItem>(legacyItem).delivery)

        val currentRead = json.decodeFromString(
            AppServerClientMethods.McpServerResourceRead.paramsSerializer,
            """{"server":"drive","uri":"file://one","connectorId":"connector-1","originCallId":"call-1"}""",
        )
        assertEquals("connector-1", currentRead.connectorId)
        assertEquals("call-1", currentRead.originCallId)
        val legacyRead = json.decodeFromString(
            AppServerClientMethods.McpServerResourceRead.paramsSerializer,
            """{"server":"drive","uri":"file://one"}""",
        )
        assertNull(legacyRead.connectorId)
        assertNull(legacyRead.originCallId)

        val response = json.decodeFromString(
            AppServerClientMethods.McpServerResourceRead.responseSerializer,
            """{"contents":[],"originCallId":"call-1"}""",
        )
        assertEquals("call-1", response.originCallId)

        val requirements = json.decodeFromString(
            AppServerClientMethods.ConfigRequirementsRead.responseSerializer,
            """{"requirements":{"allowAppshots":true,"allowRemoteControl":false,"allowLoginShell":true}}""",
        ).requirements
        assertEquals(true, requirements?.allowAppshots)
        assertEquals(false, requirements?.allowRemoteControl)
        assertNull(
            json.decodeFromString(
                AppServerClientMethods.ConfigRequirementsRead.responseSerializer,
                "{}",
            ).requirements,
        )
    }
}
