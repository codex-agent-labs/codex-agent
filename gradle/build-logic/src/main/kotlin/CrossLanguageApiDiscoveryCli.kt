import java.io.File

public fun main(arguments: Array<String>) {
    check(arguments.size == 10) { "Cross-language API discovery requires exactly ten arguments" }
    val nativeKlib = File(arguments[0])
    val wasmKlib = File(arguments[1])
    val marker = arguments[2]
    val boundaries = File(arguments[3]).readCrossLanguageStrings()
    val exclusionAnnotation = arguments[4]
    val excludedTypes = File(arguments[5]).readCrossLanguageStrings()
    val dataClassNames = File(arguments[6]).readCrossLanguageStrings()
    val singletonObjectNames = File(arguments[7]).readCrossLanguageStrings()
    val companionObjectNames = File(arguments[8]).readCrossLanguageStrings()
    val output = File(arguments[9])
    fun discover(klib: File) = discoverCrossLanguageApi(
        klib = klib,
        markerAnnotation = marker,
        allowedBoundaryTypes = boundaries,
        memberExclusionAnnotation = exclusionAnnotation,
        requiredExcludedReachableTypes = excludedTypes,
        dataClassNames = dataClassNames,
        singletonObjectNames = singletonObjectNames,
        companionObjectNames = companionObjectNames,
    )
    val nativeReport = discover(nativeKlib)
    val wasmReport = discover(wasmKlib)
    output.writeCrossLanguageApiReport(requireMatchingCrossLanguageApiReports(nativeReport, wasmReport))
}

internal fun requireMatchingCrossLanguageApiReports(
    nativeReport: CrossLanguageApiReport,
    wasmReport: CrossLanguageApiReport,
): CrossLanguageApiReport {
    check(nativeReport == wasmReport) {
        "Cross-language API differs between Native and Wasm compiler metadata"
    }
    return nativeReport
}
