package io.github.codex_agent_labs.codexagent.app.runtime.bootstrap

import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import io.github.codex_agent_labs.codexagent.appserver.runtime.CodexJsonLine
import io.github.codex_agent_labs.codexagent.appserver.runtime.CodexRuntimeConfiguration
import io.github.codex_agent_labs.codexagent.appserver.runtime.CodexRuntimeEvent
import io.github.codex_agent_labs.codexagent.appserver.runtime.RuntimeArchitecture
import io.github.codex_agent_labs.codexagent.appserver.runtime.RuntimeEnvironment
import io.github.codex_agent_labs.codexagent.appserver.runtime.RuntimeKernel
import java.io.File
import java.net.URI
import java.net.Socket
import java.nio.charset.StandardCharsets
import java.util.Base64
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.filterIsInstance
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okio.FileSystem
import okio.Path
import okio.buffer

class AndroidRuntimeHostTest {
    @Test
    fun processBuilderRuntimeFramesUtf8AndClosesIdempotently(): Unit = runBlocking {
        val directory = temporaryDirectory()
        val executable = directory / "app-server"
        val certificate = directory / "system-ca.pem"
        val privateDirectory = directory / "private"
        val logsDatabase = privateDirectory / "codex" / "logs_2.sqlite"
        val logsTemplate = directory / "logs-template.sqlite"
        FileSystem.SYSTEM.sink(executable).buffer().use {
            it.writeUtf8(
                "#!/bin/sh\n" +
                    "head -c 262144 /dev/zero >&2\n" +
                    "cp \"$logsTemplate\" \"$logsDatabase\"\n" +
                    "while IFS= read -r line; do printf '%s\\n' \"${'$'}line\"; done\n",
            )
        }
        FileSystem.SYSTEM.sink(certificate).buffer().use { it.writeUtf8("test certificate") }
        assertTrue(File(executable.toString()).setExecutable(true))
        BundledSQLiteDriver().open(logsTemplate.toString()).close()

        var bundlePath: String? = null
        val runtime = AndroidCodexRuntime(
            CodexRuntimeConfiguration(
                executable = executable,
                packagedRuntimeEnvironment = null,
                applicationDirectory = directory / "home",
                privateDirectory = privateDirectory,
                temporaryDirectory = directory / "tmp",
                certificateSources = listOf(certificate),
                sqliteDriver = BundledSQLiteDriver(),
                platformEnvironment = mapOf("PATH" to "/usr/bin:/bin"),
                proxyPassword = "host-test-secret",
            ),
            startProcess = { builder ->
                bundlePath = checkNotNull(builder.environment()["SSL_CERT_FILE"])
                builder.start()
            },
        )
        try {
            runtime.start()
            val received = async {
                withTimeout(5_000) {
                    runtime.events.filterIsInstance<CodexRuntimeEvent.Received>().first()
                }
            }
            val line = CodexJsonLine("""{"text":"Grüezi 👋"}""")
            runtime.send(line)
            assertEquals(line, received.await().line)
        } finally {
            runtime.close()
            runtime.close()
            assertTrue(!File(checkNotNull(bundlePath)).exists())
            FileSystem.SYSTEM.deleteRecursively(directory, mustExist = false)
        }
    }

    @Test
    fun closeDuringProcessLaunchReclaimsTheLateProcess(): Unit = runBlocking {
        val directory = temporaryDirectory()
        val executable = directory / "app-server"
        val certificate = directory / "system-ca.pem"
        val privateDirectory = directory / "private"
        FileSystem.SYSTEM.write(executable) {
            writeUtf8("#!/bin/sh\nwhile :; do sleep 1; done\n")
        }
        FileSystem.SYSTEM.write(certificate) { writeUtf8("test certificate") }
        assertTrue(File(executable.toString()).setExecutable(true))

        val launchEntered = CompletableDeferred<Unit>()
        val releaseLaunch = CompletableDeferred<Unit>()
        var launchedProcess: Process? = null
        var bundlePath: String? = null
        val runtime = AndroidCodexRuntime(
            CodexRuntimeConfiguration(
                executable = executable,
                packagedRuntimeEnvironment = null,
                applicationDirectory = directory / "home",
                privateDirectory = privateDirectory,
                temporaryDirectory = directory / "tmp",
                certificateSources = listOf(certificate),
                sqliteDriver = BundledSQLiteDriver(),
                platformEnvironment = mapOf("PATH" to "/usr/bin:/bin"),
                proxyPassword = "host-test-secret",
            ),
            startProcess = { builder ->
                bundlePath = checkNotNull(builder.environment()["SSL_CERT_FILE"])
                launchEntered.complete(Unit)
                releaseLaunch.await()
                builder.start().also { launchedProcess = it }
            },
        )
        try {
            val start = async { runCatching { runtime.start() }.exceptionOrNull() }
            launchEntered.await()
            assertTrue(File(checkNotNull(bundlePath)).isFile)
            runtime.close()
            releaseLaunch.complete(Unit)

            assertIs<IllegalStateException>(start.await())
            assertTrue(launchedProcess?.isAlive == false)
            assertTrue(!File(checkNotNull(bundlePath)).exists())
        } finally {
            releaseLaunch.complete(Unit)
            runtime.close()
            launchedProcess?.destroyForcibly()
            FileSystem.SYSTEM.deleteRecursively(directory, mustExist = false)
        }
    }

    @Test
    fun closingOneRuntimeKeepsAnotherRuntimesCertificateBundle(): Unit = runBlocking {
        val directory = temporaryDirectory()
        val executable = directory / "app-server"
        val certificate = directory / "system-ca.pem"
        val privateDirectory = directory / "private"
        val logsDatabase = privateDirectory / "codex" / "logs_2.sqlite"
        val logsTemplate = directory / "logs-template.sqlite"
        FileSystem.SYSTEM.write(executable) {
            writeUtf8(
                "#!/bin/sh\n" +
                    "if [ ! -e '$logsDatabase' ]; then cp '$logsTemplate' '$logsDatabase'; fi\n" +
                    "while IFS= read -r line; do printf '%s\\n' \"${'$'}line\"; done\n",
            )
        }
        FileSystem.SYSTEM.write(certificate) { writeUtf8("test certificate") }
        assertTrue(File(executable.toString()).setExecutable(true))
        BundledSQLiteDriver().open(logsTemplate.toString()).close()
        val bundlePaths = mutableListOf<String>()
        val runtimes = (1..2).map {
            AndroidCodexRuntime(
                CodexRuntimeConfiguration(
                    executable = executable,
                    packagedRuntimeEnvironment = null,
                    applicationDirectory = directory / "home",
                    privateDirectory = privateDirectory,
                    temporaryDirectory = directory / "tmp",
                    certificateSources = listOf(certificate),
                    sqliteDriver = BundledSQLiteDriver(),
                    platformEnvironment = mapOf("PATH" to "/usr/bin:/bin"),
                    proxyPassword = "host-test-secret",
                ),
                startProcess = { builder ->
                    bundlePaths += checkNotNull(builder.environment()["SSL_CERT_FILE"])
                    builder.start()
                },
            )
        }
        try {
            runtimes.forEach { it.start() }
            assertEquals(2, bundlePaths.distinct().size)
            runtimes.first().close()
            assertTrue(!File(bundlePaths.first()).exists())
            assertTrue(File(bundlePaths.last()).isFile)
            val received = async {
                withTimeout(5_000) {
                    runtimes.last().events.filterIsInstance<CodexRuntimeEvent.Received>().first()
                }
            }
            val line = CodexJsonLine("""{"text":"still running"}""")
            runtimes.last().send(line)
            assertEquals(line, received.await().line)
        } finally {
            runtimes.forEach { it.close() }
            FileSystem.SYSTEM.deleteRecursively(directory, mustExist = false)
        }
    }

    @Test
    fun tamperedPackagedRuntimeIsRejectedBeforeProcessLaunch(): Unit = runBlocking {
        val directory = temporaryDirectory()
        val executable = directory / "libcodex_app_server.so"
        FileSystem.SYSTEM.write(executable) { writeUtf8("#!/bin/sh\nexit 0\n") }
        assertTrue(File(executable.toString()).setExecutable(true))
        var launched = false
        val runtime = AndroidCodexRuntime(
            CodexRuntimeConfiguration(
                executable = executable,
                packagedRuntimeEnvironment = RuntimeEnvironment(
                    RuntimeKernel.LINUX,
                    RuntimeArchitecture.AARCH64,
                    true,
                ),
                applicationDirectory = directory / "home",
                privateDirectory = directory / "private",
                temporaryDirectory = directory / "tmp",
                certificateSources = emptyList(),
                sqliteDriver = BundledSQLiteDriver(),
                platformEnvironment = mapOf("PATH" to "/usr/bin:/bin"),
                proxyPassword = "host-test-secret",
            ),
            startProcess = {
                launched = true
                error("tampered runtime must not launch")
            },
        )
        try {
            val failure = runCatching { runtime.start() }.exceptionOrNull()
            assertIs<IllegalStateException>(failure)
            assertTrue(failure.message.orEmpty().contains("checksum is invalid"))
            assertTrue(!launched)
        } finally {
            runtime.close()
            FileSystem.SYSTEM.deleteRecursively(directory, mustExist = false)
        }
    }

    @Test
    fun loopbackProxyRequiresAuthenticationAndRejectsPrivateDestinations() {
        val password = "proxy-test-secret"
        val proxy = LoopbackConnectProxy(password)
        try {
            val uri = URI(proxy.url)
            assertEquals("127.0.0.1", uri.host)
            assertTrue(uri.port > 0)
            assertTrue(
                proxyRequest(uri, "CONNECT example.com:443 HTTP/1.1\r\n\r\n")
                    .startsWith("HTTP/1.1 407"),
            )

            val authorization = Base64.getEncoder()
                .encodeToString("codex:$password".toByteArray(StandardCharsets.UTF_8))
            assertTrue(
                proxyRequest(
                    uri,
                    "CONNECT 127.0.0.1:443 HTTP/1.1\r\n" +
                        "Proxy-Authorization: Basic $authorization\r\n\r\n",
                ).startsWith("HTTP/1.1 403"),
            )
        } finally {
            proxy.close()
            proxy.close()
        }
    }
}

private fun proxyRequest(proxy: URI, request: String): String =
    Socket(proxy.host, proxy.port).use { socket ->
        socket.soTimeout = 5_000
        socket.outputStream.write(request.toByteArray(StandardCharsets.US_ASCII))
        socket.outputStream.flush()
        socket.inputStream.bufferedReader(StandardCharsets.US_ASCII).readLine()
    }

private fun temporaryDirectory(): Path =
    (FileSystem.SYSTEM_TEMPORARY_DIRECTORY / "codex-android-runtime-${Random.nextLong()}").also {
        FileSystem.SYSTEM.createDirectories(it)
    }
