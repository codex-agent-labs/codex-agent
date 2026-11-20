package io.github.codex_agent_labs.codexagent.appserver.runtime

import androidx.sqlite.SQLiteConnection
import androidx.sqlite.execSQL

internal fun Throwable.visibleMessage(): String =
    message?.take(500)?.takeIf(String::isNotBlank) ?: this::class.simpleName ?: "Codex failure"

internal fun installRuntimeLogPrivacyGuard(database: SQLiteConnection) {
    database.execSQL("PRAGMA secure_delete=ON")
    database.execSQL("BEGIN IMMEDIATE")
    try {
        // The runtime owns migrations, including a logs-table replacement. Wait for
        // its final schema instead of creating a table or guarding an obsolete one.
        database.prepare("SELECT feedback_log_body FROM logs LIMIT 0").use { it.step() }
        database.execSQL("DROP TRIGGER IF EXISTS codex_agent_drop_runtime_logs")
        database.execSQL("DELETE FROM logs")
        database.execSQL(
            """
            CREATE TRIGGER codex_agent_drop_runtime_logs
            BEFORE INSERT ON logs
            BEGIN
                SELECT RAISE(IGNORE);
            END
            """.trimIndent(),
        )
        database.execSQL("COMMIT")
    } catch (error: Throwable) {
        runCatching { database.execSQL("ROLLBACK") }
        throw error
    }
    checkpointAndTruncate(database)
    database.execSQL("VACUUM")
    checkpointAndTruncate(database)
}

private fun checkpointAndTruncate(database: SQLiteConnection) {
    database.prepare("PRAGMA wal_checkpoint(TRUNCATE)").use { statement ->
        check(statement.step()) { "SQLite checkpoint returned no status" }
        check(statement.getLong(0) == 0L) { "SQLite checkpoint could not acquire the database lock" }
    }
}
