@file:kotlin.js.JsModule("node:fs")
@file:OptIn(kotlin.js.ExperimentalWasmJsInterop::class)

package io.github.codex_agent_labs.codexmobile.appserver.runtime

import kotlin.js.JsAny

internal external fun realpathSync(path: String): String
internal external fun statSync(path: String): WasmNodeStats
internal external fun lstatSync(path: String): WasmNodeStats
internal external fun existsSync(path: String): Boolean
internal external fun accessSync(path: String, mode: Int)
internal external fun readFileSync(path: String): JsAny
internal external fun openSync(path: String, flags: String): Int
internal external fun fstatSync(descriptor: Int): WasmNodeStats
internal external fun readSync(
    descriptor: Int,
    buffer: JsAny,
    offset: Int,
    length: Int,
    position: JsAny?,
): Int
internal external fun closeSync(descriptor: Int)
internal external fun writeFileSync(path: String, value: JsAny)
internal external fun writeFileSync(path: String, value: JsAny, options: JsAny)
internal external fun chmodSync(path: String, mode: Int)
internal external fun mkdtempSync(prefix: String): String
internal external fun rmSync(path: String, options: JsAny)
internal external fun renameSync(source: String, destination: String)
internal external fun symlinkSync(target: String, path: String)
internal external fun mkdirSync(path: String, options: JsAny)
internal external fun mkdirSync(path: String)
internal external fun readdirSync(path: String): JsAny
