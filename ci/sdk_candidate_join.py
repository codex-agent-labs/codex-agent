"""Offline SDK candidate join, including its exact default Runtime authorizations.

Inputs are the existing exact-byte forwarders' outputs. The protected caller
must independently approve S1048 pins and authenticate official custody first.
This joins content; it never elects authority, signs, builds or publishes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.sdk_candidate_admission import _REPOSITORY, _SECRETS, _TOKENS, candidate_object_root
from ci.sdk_candidate_semantics import _package_compatibility, _selection, verify_sdk_candidate_semantics
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_sha256, sha256_bytes, sha256_file,
)
from ci.products.registry import COMPONENTS_BY_IDENTITY, NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from ci.products.plan import _upstream_record
from ci.products.restore import (
    memoized_file_inventory as regular_file_inventory, object_relative_path,
    verification_scoped,
)
from ci.products.runtime_library_authorization import _LIBRARY_PATHS
from ci.products.sdk_campaign_index import verify_release_sdk_campaign_objects
from ci.products.sdk_runtime_root import verify_external_library_authorization
from ci.products.signing_isolation import require_no_signing_secret


def _read(path, limit=64 * 1024):
    return read_regular_file_bytes(path, max_bytes=limit, reject_symlink_parents=True)


def _verify_default_runtime(library: Path, evidence: Path, root_bytes: bytes,
                            compatibility: dict, target: str) -> dict:
    # The loader verifier checks both signatures, the delegated keyring, exact
    # host/Contract/ABI/ranges and actual library digest. Candidates additionally
    # require the embedded default, not merely a compatible external update.
    claim = verify_external_library_authorization(evidence,
        sdk_pinned_root_public_key=root_bytes, sdk_compatibility=compatibility,
        target=target, library_snapshot=library)
    defaults = compatibility["runtime"]
    variant = next(row for row in defaults["embeddedVariants"] if row["target"] == target)
    if (claim["runtimeVersion"] != defaults["defaultRuntimeVersion"]
            or claim["aggregateManifestSha256"] != defaults["defaultManifestSha256"]
            or claim["runtimeIdentity"]["componentId"] != variant["componentId"]
            or any(claim[left] != variant[right] for left, right in (
                ("runtimeLibrarySha256", "runtimeLibrarySha256"),
                ("variantBundleSha256", "bundleSha256"), ("variantManifestSha256", "manifestSha256")))):
        raise ValueError("SDK candidate authorization differs from its exact default Runtime")
    return claim


@verification_scoped
def join_sdk_candidate(promoted_catalog: Path, forwarded_objects: Path, forwarded_maven: Path,
                       forwarded_runtime: Path, selection: dict, *,
                       parity_archive: Path, parity_phase_identities: Path,
                       use_promoted_objects: bool = False) -> dict:
    require_no_signing_secret(os.environ)
    if (_TOKENS | _SECRETS) & os.environ.keys():
        raise ValueError("SDK candidate join must not receive token or signing secret")
    approved = canonical_json_bytes(selection)
    selection = require_exact_keys(selection, {"schemaVersion", "sdk", "runtime"},
                                   "SDK candidate selection")
    if type(selection["schemaVersion"]) is not int or selection["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate selection schema")
    pins, dependencies, parity_pins = _selection(selection["sdk"])
    runtime_pins = require_exact_keys(selection["runtime"], {
        "inventorySha256", "rootPublicKeySha256"}, "SDK candidate Runtime pins")
    for field, digest in runtime_pins.items():
        require_sha256(digest, "SDK candidate Runtime " + field)
    runtime, objects = Path(forwarded_runtime), Path(forwarded_objects)
    object_root = candidate_object_root(promoted_catalog, objects, use_promoted_objects)
    original_files = {Path(path): regular_file_inventory(path)
                      for path in (promoted_catalog, objects, forwarded_maven)}
    runtime_files = regular_file_inventory(runtime)
    if sha256_bytes(canonical_json_bytes(runtime_files)) != runtime_pins["inventorySha256"]:
        raise ValueError("SDK candidate Runtime forwarding differs from S1048 inventory")
    root_bytes = _read(runtime / "sdk-runtime-root.pub", 4096)
    if sha256_bytes(root_bytes) != runtime_pins["rootPublicKeySha256"]:
        raise ValueError("SDK candidate Runtime root differs from S1048 approval")

    # Complete SDK admission stays unscoped, including all62 originals/all112
    # parity identities. Only the following resource consumption is narrow.
    joined = verify_sdk_candidate_semantics(promoted_catalog, objects, forwarded_maven,
        selection["sdk"], parity_archive=parity_archive, parity_phase_identities=parity_phase_identities,
        use_promoted_objects=use_promoted_objects)
    raw_pins = _read(objects / "object-pins.json")
    if sha256_bytes(raw_pins) != pins["expected_object_pins_sha256"]:
        raise ValueError("SDK candidate original pins changed after semantic verification")
    by_id = {PhaseInstanceId(*(row[field] for field in ("product", "component", "phase", "target"))): row
             for row in load_canonical_json_bytes(raw_pins)["objects"]}
    raw_index = _read(Path(promoted_catalog) / "product-index.json", 16 * 1024 * 1024)
    if sha256_bytes(raw_index) != pins["expected_promoted_index_sha256"]:
        raise ValueError("SDK candidate signed index changed after semantic verification")
    # The semantic gate authenticated this exact signed index and every object.
    # Reuse its existing lifetime-bound receipt proof; no new payload scan/copy.
    originals = verify_release_sdk_campaign_objects(load_canonical_json_bytes(raw_index),
        {row["buildKey"]: Path(promoted_catalog) / object_relative_path(row["buildKey"], row["receiptSha256"])
         for row in by_id.values()}, repository=_REPOSITORY)
    for language in NATIVE_BINDINGS:
        # The first producing phase embeds the root: C# binary, other native
        # packages. Bind a separate binary owner to the selected package too.
        component = COMPONENTS_BY_IDENTITY["sdk", language]
        identity = PhaseInstanceId("sdk", language, component.phases[0], component.default_target)
        row = by_id[identity]
        receipt = originals[identity]["receipt"]
        if (any(receipt[field] != row[field] for field in ("product", "component", "phase", "target"))
                or receipt["productVersion"] != pins["expected_sdk_version"]
                or [item for item in receipt["inputs"]["inventory"]
                    if item["relativePath"] == "gradle/release/keys/sdk-runtime-root.pub"] != [{
                        "relativePath": "gradle/release/keys/sdk-runtime-root.pub",
                        "bytes": len(root_bytes), "sha256": runtime_pins["rootPublicKeySha256"]}]):
            raise ValueError("SDK candidate Runtime root differs from original native producer inputs")
        if identity.phase != "package":
            package = originals[PhaseInstanceId("sdk", language, "package", component.default_target)]["receipt"]
            if _upstream_record(receipt) not in package["inputs"]["upstreamArtifacts"]:
                raise ValueError("SDK candidate package does not consume the exact root-owning binary")
    core = by_id[PhaseInstanceId("sdk", "sdk-core", "package", "common")]
    raw = _package_compatibility(object_root / object_relative_path(core["buildKey"], core["receiptSha256"]),
                                 core, core["objectSha256"], pins["expected_sdk_version"])
    if sha256_bytes(raw) != dependencies["sdkCompatibilitySha256"]:
        raise ValueError("SDK candidate compatibility changed after semantic verification")
    compatibility = load_canonical_json_bytes(raw)
    delegation = regular_file_inventory(runtime / "root-delegation")
    expected = {"sdk-runtime-root.pub", *("root-delegation/" + row["relativePath"] for row in delegation)}
    for target in NATIVE_TARGETS:
        relative = target + "/" + Path(_LIBRARY_PATHS[target]).name
        library = runtime / "library-authorizations" / relative
        evidence = library.with_name(library.name + ".evidence")
        _verify_default_runtime(library, evidence, root_bytes, compatibility, target)
        for record in delegation:
            if _read(evidence / record["relativePath"], 1024 * 1024) != _read(
                    runtime / "root-delegation" / record["relativePath"], 1024 * 1024):
                raise ValueError("SDK candidate Runtime authorizations disagree on root delegation")
        expected.add("library-authorizations/" + relative)
        expected.update("library-authorizations/" + relative + ".evidence/" + name for name in (
            *(row["relativePath"] for row in delegation),
            "runtime-library-authorization.json", "runtime-library-authorization.sig"))
    if {row["relativePath"] for row in runtime_files} != expected:
        raise ValueError("SDK candidate Runtime forwarding has extra or missing files")
    if (regular_file_inventory(runtime) != runtime_files
            or any(regular_file_inventory(path) != files for path, files in original_files.items())
            or _read(runtime / "sdk-runtime-root.pub", 4096) != root_bytes
            or sha256_file(parity_archive, reject_symlink_parents=True) != parity_pins["archiveSha256"]
            or sha256_file(parity_phase_identities, reject_symlink_parents=True) != parity_pins["phaseIdentitiesSha256"]
            or canonical_json_bytes(selection) != approved):
        raise ValueError("SDK candidate inputs changed during Runtime join")
    return {**joined, "runtimeAuthorizationTargets": list(NATIVE_TARGETS),
            "runtimeAuthorizationInventorySha256": runtime_pins["inventorySha256"],
            "sdkRuntimeRootSha256": runtime_pins["rootPublicKeySha256"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--use-promoted-objects", action="store_true")
    for name in ("promoted-catalog", "forwarded-objects", "forwarded-maven", "forwarded-runtime",
                 "selection", "parity-archive", "parity-phase-identities"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    args = vars(parser.parse_args(argv))
    raw = _read(args.pop("selection"))
    if sha256_bytes(raw) != require_sha256(args.pop("expected_selection_sha256"), "SDK candidate selection"):
        raise ValueError("SDK candidate selection differs from independent S1048 approval")
    result = join_sdk_candidate(selection=load_canonical_json_bytes(raw), **args)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
