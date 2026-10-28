"""Project an independently approved acceptance snapshot into documentation.

This reads inventories, not product bodies, and grants no reuse/release authority.
The report digest must come from the completed acceptance gate, not this command.
"""

import argparse
from pathlib import Path, PurePosixPath
import sys

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_sha256, sha256_bytes,
)
from ci.products.receipt import validate_phase_receipt
from ci.products.registry import PHASE_INSTANCE_IDS


FIELDS = ("product", "component", "phase", "target")


def approved_receipts(report_bytes, expected_sha256, captures):
    if sha256_bytes(report_bytes) != require_sha256(expected_sha256, "Approved acceptance report"):
        raise ValueError("Acceptance report differs from its independently approved digest")
    report = load_canonical_json_bytes(report_bytes)
    expected = {tuple(getattr(item, field) for field in FIELDS) for item in PHASE_INSTANCE_IDS}
    if report["result"] != "passed" or report["sdkParity"]["result"] != "passed":
        raise ValueError("Documentation requires completed product and parity acceptance")
    approved = {}
    for row in report["originalPhases"]:
        identity = tuple(row[field] for field in FIELDS)
        if identity in approved or row["state"] != "retained" or row["misses"]:
            raise ValueError("Acceptance must contain each retained original exactly once")
        approved[identity] = row
    if set(approved) != expected or report["phaseCount"] != len(expected):
        raise ValueError("Acceptance phase set is incomplete")
    found = {}

    def collect(value):
        if isinstance(value, dict):
            if {"inputs", "outputs", "buildKey", *FIELDS} <= value.keys():
                receipt = validate_phase_receipt(value)
                identity = tuple(receipt[field] for field in FIELDS)
                selected = approved.get(identity)
                if selected is None or selected["buildKey"] != receipt["buildKey"] or selected[
                    "receiptSha256"
                ] != sha256_bytes(canonical_json_bytes(receipt)):
                    raise ValueError("Receipt differs from the accepted original")
                if identity in found and found[identity] != receipt:
                    raise ValueError("Conflicting original receipts")
                found[identity] = receipt
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for capture in captures:
        collect(capture)
    if set(found) != expected:
        raise ValueError("Missing accepted original receipts")
    return report, [found[key] for key in sorted(found)]


def render(report, receipts, report_sha256):
    lines = ["# Artifact-derived acceptance matrix", "",
        "Generated from a completed Phase-9 acceptance snapshot and its exact original",
        "receipt inventories. This is evidence of built/validated artifacts, not public",
        "publication, final frozen-head acceptance, or a new authentication decision.", "",
        f"Acceptance report: `{report_sha256}`.", "",
        "## Product versions and executed validation targets", "",
        "| Product / component | Version | Validation targets |",
        "| --- | --- | --- |"]
    groups = {}
    maven = set()
    packages = set()
    for receipt in receipts:
        group = groups.setdefault((receipt["product"], receipt["component"]), (set(), set()))
        group[0].add(receipt["productVersion"])
        if receipt["phase"] == "validation":
            group[1].add(receipt["target"])
        for output in receipt["outputs"]:
            path = PurePosixPath(output["relativePath"])
            if path.suffix == ".pom":
                parts = path.parts
                start = parts.index("io") if "io" in parts else -1
                if start < 0 or parts[start:start + 3] != ("io", "github", "codex-agent-labs"):
                    raise ValueError("Unexpected Maven publication group")
                artifact, version = parts[-3:-1]
                if path.name != f"{artifact}-{version}.pom" or version != receipt["productVersion"]:
                    raise ValueError("Maven identity differs from its owning receipt")
                maven.add((receipt["product"], f"io.github.codex-agent-labs:{artifact}:{version}"))
            if (receipt["product"] == "sdk" and receipt["phase"] == "package"
                    and path.name.endswith((".whl", ".tar.gz", ".tgz", ".crate", ".nupkg", ".zip"))):
                packages.add((receipt["component"], path.name))
    for (product, component), (versions, targets) in sorted(groups.items()):
        if len(versions) != 1:
            raise ValueError("Mixed component versions in accepted snapshot")
        lines.append(f"| {product} / {component} | {next(iter(versions))} | {', '.join(sorted(targets)) or 'aggregation only'} |")
    lines += ["", "## Maven coordinates", "", "| Owner | Coordinate |", "| --- | --- |"]
    lines += [f"| {owner} | `{coordinate}` |" for owner, coordinate in sorted(maven)]
    lines += ["", "## SDK package filenames", "", "| Component | Package |", "| --- | --- |"]
    lines += [f"| {component} | `{name}` |" for component, name in sorted(packages)]
    parity = report["sdkParity"]
    lines += ["", f"Parity: {parity['languageCount']} languages; {parity['satisfied']} satisfied claims; "
              f"{parity['excluded']} explicit exclusions; {parity['scenarioCount']} scenarios.", "",
        "Regenerate with `python3 -m docs.artifact_matrix --report <accepted-sdk-report.json>`",
        "`--expected-report-sha256 <independently-approved-digest> --capture <original-proof.json>`",
        "`--capture <original-qualification.json> --capture <sdk-completion.json>`.",
        "Use `--check docs/ARTIFACT_MATRIX.md` to check this snapshot without writing files.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--capture", type=Path, action="append", required=True)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    read = lambda path: read_regular_file_bytes(path, max_bytes=32 * 1024 * 1024, reject_symlink_parents=True)
    report, receipts = approved_receipts(read(args.report), args.expected_report_sha256,
        [load_canonical_json_bytes(read(path)) for path in args.capture])
    result = render(report, receipts, args.expected_report_sha256)
    if args.check:
        if read(args.check) != result.encode():
            raise ValueError("Artifact documentation differs from approved original inventories")
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
