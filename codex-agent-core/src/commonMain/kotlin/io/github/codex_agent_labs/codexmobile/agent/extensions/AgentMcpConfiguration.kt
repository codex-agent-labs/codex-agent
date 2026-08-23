package io.github.codex_agent_labs.codexmobile.agent

private const val RUST_DURATION_SECONDS_LIMIT: Double = 1.8446744073709552E19

public data class AgentMcpServerConfiguration(
    public val name: String,
    public val transport: AgentMcpTransport,
    public val authentication: AgentMcpAuthentication? = null,
    public val environmentId: String = "local",
    public val isEnabled: Boolean = true,
    public val isRequired: Boolean = false,
    public val supportsParallelToolCalls: Boolean = false,
    public val omitToolsFrom: List<AgentMcpToolExposureSurface>? = null,
    public val startupTimeoutSeconds: Double? = null,
    public val toolTimeoutSeconds: Double? = null,
    public val defaultToolApproval: AgentMcpToolApproval? = null,
    public val enabledTools: List<String>? = null,
    public val disabledTools: List<String>? = null,
    public val scopes: List<String>? = null,
    public val oauth: AgentMcpOauthConfiguration? = null,
    public val oauthResource: String? = null,
    public val tools: Map<String, AgentMcpToolConfiguration> = emptyMap(),
) {
    init {
        require(name.isNotEmpty() && name.all { it.isAsciiLetterOrDigit() || it == '-' || it == '_' }) {
            "MCP server name may contain only ASCII letters, numbers, '-', and '_'"
        }
        require(environmentId.isNotBlank()) { "MCP environment ID must not be blank" }
        require(startupTimeoutSeconds.isSupportedMcpTimeout()) {
            "MCP startup timeout must be positive and within Codex's supported range"
        }
        require(toolTimeoutSeconds.isSupportedMcpTimeout()) {
            "MCP tool timeout must be positive and within Codex's supported range"
        }
        when (transport) {
            is AgentMcpTransport.Stdio -> {
                require(authentication == null) { "MCP stdio servers do not support authentication" }
                require(oauth == null) { "MCP stdio servers do not support OAuth configuration" }
                require(oauthResource == null) { "MCP stdio servers do not support an OAuth resource" }
            }
            is AgentMcpTransport.Http -> require(
                transport.headersHelper == null || environmentId == "local",
            ) { "MCP HTTP headers helpers are only supported for local servers" }
        }
    }
}

private fun Double?.isSupportedMcpTimeout(): Boolean =
    this == null || isFinite() && this > 0.0 && this < RUST_DURATION_SECONDS_LIMIT

public sealed interface AgentMcpTransport {
    public data class Stdio(
        public val command: String,
        public val arguments: List<String> = emptyList(),
        public val workingDirectory: String? = null,
        public val environment: Map<String, String>? = null,
        public val forwardedEnvironment: List<AgentMcpEnvironmentVariable> = emptyList(),
    ) : AgentMcpTransport {
        init {
            require(command.isNotBlank()) { "MCP command must not be blank" }
        }
    }

    public data class Http(
        public val url: String,
        public val bearerTokenEnvironmentVariable: String? = null,
        public val headers: Map<String, String>? = null,
        public val environmentHeaders: Map<String, String>? = null,
        public val headersHelper: String? = null,
    ) : AgentMcpTransport {
        init {
            require(url.isSafeMcpHttpUrl()) {
                "MCP HTTP URL must use HTTPS or a loopback HTTP address"
            }
            require(bearerTokenEnvironmentVariable == null || bearerTokenEnvironmentVariable.isNotBlank()) {
                "MCP bearer-token environment variable must not be blank"
            }
            require(headersHelper == null || headersHelper.isNotBlank()) { "MCP headers helper must not be blank" }
        }
    }
}

public data class AgentMcpEnvironmentVariable(
    public val name: String,
    public val source: AgentMcpEnvironmentSource? = null,
) {
    init {
        require(name.isNotBlank()) { "MCP environment variable name must not be blank" }
    }
}

public enum class AgentMcpEnvironmentSource { LOCAL, REMOTE }

public enum class AgentMcpAuthentication { OAUTH, CHAT_GPT }

public enum class AgentMcpToolApproval { AUTO, PROMPT, WRITES, APPROVE }

public enum class AgentMcpToolExposureSurface { CODE_MODE, DEFERRED, DIRECT }

public data class AgentMcpOauthConfiguration(
    public val clientId: String? = null,
    public val callbackPort: Int? = null,
) {
    init {
        require(callbackPort == null || callbackPort in 1..65535) { "MCP OAuth callback port is invalid" }
    }
}

public data class AgentMcpToolConfiguration(
    public val approval: AgentMcpToolApproval? = null,
)

private fun String.isSafeMcpHttpUrl(): Boolean {
    if (any { it.isWhitespace() || it.isISOControl() }) return false
    val scheme = when {
        startsWith("https://") -> "https"
        startsWith("http://") -> "http"
        else -> return false
    }
    val authorityStart = scheme.length + 3
    val authorityEnd = indexOfAny(charArrayOf('/', '?', '#'), authorityStart)
        .takeIf { it >= 0 } ?: length
    val authority = substring(authorityStart, authorityEnd)
    if (authority.isEmpty() || '@' in authority) return false

    val host = if (authority.startsWith('[')) {
        val closingBracket = authority.indexOf(']')
        if (closingBracket <= 1 || !authority.validMcpPortAfter(closingBracket + 1)) return false
        authority.substring(1, closingBracket).takeIf { address ->
            ':' in address && address.any(Char::isAsciiHexDigit) &&
                address.all { it.isAsciiHexDigit() || it == ':' || it == '.' }
        } ?: return false
    } else {
        if (authority.count { it == ':' } > 1) return false
        val separator = authority.indexOf(':')
        if (separator >= 0 && !authority.validMcpPortAfter(separator)) return false
        authority.substringBefore(':').takeIf(String::isValidMcpRegisteredHost) ?: return false
    }
    return scheme == "https" || host.equals("localhost", ignoreCase = true) ||
        host == "127.0.0.1" || host == "::1"
}

private fun String.validMcpPortAfter(separator: Int): Boolean {
    if (separator == length) return true
    if (getOrNull(separator) != ':') return false
    val port = substring(separator + 1)
    return port.isNotEmpty() && port.all(Char::isDigit) &&
        port.toIntOrNull()?.let { it in 1..65535 } == true
}

private fun String.isValidMcpRegisteredHost(): Boolean {
    var index = 0
    var hasName = false
    while (index < length) {
        val character = get(index)
        when {
            character.isAsciiLetterOrDigit() -> {
                hasName = true
                index += 1
            }
            character == '%' -> {
                if (getOrNull(index + 1)?.isAsciiHexDigit() != true ||
                    getOrNull(index + 2)?.isAsciiHexDigit() != true
                ) return false
                hasName = true
                index += 3
            }
            character in "-._~!$&'()*+,;=" -> index += 1
            else -> return false
        }
    }
    return hasName
}

private fun Char.isAsciiLetterOrDigit(): Boolean =
    this in 'a'..'z' || this in 'A'..'Z' || this in '0'..'9'

private fun Char.isAsciiHexDigit(): Boolean = this in '0'..'9' || lowercaseChar() in 'a'..'f'
