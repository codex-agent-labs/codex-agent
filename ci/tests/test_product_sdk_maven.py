from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile

from ci.products.sdk_maven import (
    COMPONENT_CARRIERS,
    COMPONENT_ARTIFACTS,
    KLIB_RESOURCE,
    RESOURCE,
    _inject_archive,
    _verify_archive,
    package_sdk_maven,
)


def _zip(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in sorted(members.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, contents)


class SdkMavenPackagingTest(unittest.TestCase):
    def test_every_component_packages_its_exact_carrier_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            version = "0.2.0"
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(b'{"schemaVersion":1}\n')
            for component, carriers in COMPONENT_CARRIERS.items():
                with self.subTest(component=component):
                    source = root / f"source-{component}"
                    group = source / "io/github/codex-agent-labs"
                    for artifact, (kind, _) in carriers.items():
                        directory = group / artifact / version
                        archive = directory / f"{artifact}-{version}.{kind}"
                        if kind == "aar":
                            classes = root / f"{artifact}-classes.jar"
                            _zip(classes, {"payload": artifact.encode()})
                            _zip(archive, {"classes.jar": classes.read_bytes()})
                        else:
                            _zip(archive, {"payload": artifact.encode()})
                        contents = archive.read_bytes()
                        (directory / f"{artifact}-{version}.module").write_text(json.dumps({
                            "variants": [{"files": [{
                                "name": archive.name,
                                "url": archive.name,
                                "size": len(contents),
                                **{
                                    algorithm: hashlib.new(algorithm, contents).hexdigest()
                                    for algorithm in ("md5", "sha1", "sha256", "sha512")
                                },
                            }]}],
                        }) + "\n", encoding="utf-8")
                    for artifact in COMPONENT_ARTIFACTS[component] - set(carriers):
                        directory = group / artifact / version
                        directory.mkdir(parents=True)
                        (directory / f"{artifact}-{version}.pom").write_text("<project/>\n", encoding="utf-8")
                    output = root / f"output-{component}"
                    package_sdk_maven(
                        source, output, compatibility,
                        "io.github.codex-agent-labs", version, component,
                    )
                    for artifact, (kind, resource) in carriers.items():
                        packaged = output / "io/github/codex-agent-labs" / artifact / version / \
                            f"{artifact}-{version}.{kind}"
                        _verify_archive(packaged, kind, resource, compatibility.read_bytes())

    def test_direct_archive_carriers_require_one_exact_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = b'{"schemaVersion":1}\n'
            for kind, resource in (("jar", RESOURCE), ("klib", KLIB_RESOURCE)):
                with self.subTest(kind=kind):
                    archive = root / f"carrier.{kind}"
                    _zip(archive, {"payload": b"binary"})
                    _inject_archive(archive, kind, resource, compatibility)
                    _verify_archive(archive, kind, resource, compatibility)

                    _zip(archive, {"wrong/sdk-compatibility.json": compatibility})
                    with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                        _verify_archive(archive, kind, resource, compatibility)

                    with zipfile.ZipFile(archive, "w") as output:
                        output.writestr(resource, compatibility)
                        output.writestr(resource, compatibility)
                    with self.assertRaisesRegex(ValueError, "duplicate"):
                        _verify_archive(archive, kind, resource, compatibility)

    def test_android_package_injects_nested_resource_and_refreshes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            version = "0.2.0"
            artifact = "codex-agent-runtime-android"
            directory = source / "io/github/codex-agent-labs" / artifact / version
            classes = root / "classes.jar"
            _zip(classes, {"codex/Agent.class": b"class"})
            aar = directory / f"{artifact}-{version}.aar"
            _zip(aar, {"AndroidManifest.xml": b"manifest", "classes.jar": classes.read_bytes()})
            module = directory / f"{artifact}-{version}.module"
            module.write_text(json.dumps({"variants": [{"files": [{
                "name": aar.name,
                "url": aar.name,
                "size": aar.stat().st_size,
                "md5": hashlib.md5(aar.read_bytes()).hexdigest(),
                "sha1": hashlib.sha1(aar.read_bytes()).hexdigest(),
                "sha256": hashlib.sha256(aar.read_bytes()).hexdigest(),
                "sha512": hashlib.sha512(aar.read_bytes()).hexdigest(),
            }]}]}) + "\n", encoding="utf-8")
            for primary in (aar, module):
                for suffix in (".md5", ".sha1", ".sha256", ".sha512"):
                    primary.with_name(primary.name + suffix).write_text("stale\n", encoding="ascii")
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(b'{"schemaVersion":1}\n')

            output = root / "output"
            package_sdk_maven(
                source, output, compatibility, "io.github.codex-agent-labs", version, "sdk-android",
            )
            packaged = output / aar.relative_to(source)
            _verify_archive(packaged, "aar", RESOURCE, compatibility.read_bytes())
            metadata = json.loads((output / module.relative_to(source)).read_text(encoding="utf-8"))
            record = metadata["variants"][0]["files"][0]
            self.assertEqual(packaged.stat().st_size, record["size"])
            self.assertEqual(hashlib.sha256(packaged.read_bytes()).hexdigest(), record["sha256"])
            self.assertEqual(
                hashlib.sha256(packaged.read_bytes()).hexdigest(),
                packaged.with_name(packaged.name + ".sha256").read_text().strip(),
            )

            _zip(aar, {
                "classes.jar": classes.read_bytes(),
                RESOURCE: b"untrusted",
            })
            with self.assertRaisesRegex(ValueError, "raw Android binary"):
                package_sdk_maven(
                    source, root / "outer-declaration", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )

    def test_raw_carrier_with_compatibility_and_incomplete_component_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            version = "0.2.0"
            artifact = "codex-agent-runtime-android"
            directory = source / "io/github/codex-agent-labs" / artifact / version
            classes = root / "classes.jar"
            _zip(classes, {RESOURCE: b"untrusted"})
            _zip(directory / f"{artifact}-{version}.aar", {"classes.jar": classes.read_bytes()})
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(b'{"schemaVersion":1}\n')
            with self.assertRaisesRegex(ValueError, "raw Android binary"):
                package_sdk_maven(
                    source, root / "output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )

            empty = root / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(ValueError, "artifact inventory mismatch"):
                package_sdk_maven(
                    empty, root / "second-output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-core",
                )

    def test_component_carrier_contract_is_exact(self) -> None:
        self.assertEqual({"sdk-core", "sdk-android", "sdk-ios"}, set(COMPONENT_CARRIERS))
        self.assertEqual(12, len(COMPONENT_CARRIERS["sdk-core"]))
        self.assertEqual(1, len(COMPONENT_CARRIERS["sdk-android"]))
        self.assertEqual(3, len(COMPONENT_CARRIERS["sdk-ios"]))
        self.assertNotIn("codex-agent-runtime-desktop", {
            artifact for carriers in COMPONENT_CARRIERS.values() for artifact in carriers
        })
        self.assertEqual(
            set(COMPONENT_CARRIERS["sdk-core"]) | {"codex-agent-bom"},
            COMPONENT_ARTIFACTS["sdk-core"],
        )

    def test_archive_paths_and_module_ownership_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("bad\nname", "a//b", "a/./b"):
                archive = root / "bad.jar"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(name, b"payload")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unsafe"):
                    _verify_archive(archive, "jar", RESOURCE, b"compatibility")

            source = root / "source"
            version = "0.2.0"
            artifact = "codex-agent-runtime-android"
            directory = source / "io/github/codex-agent-labs" / artifact / version
            classes = root / "classes.jar"
            _zip(classes, {"payload": b"class"})
            aar = directory / f"{artifact}-{version}.aar"
            _zip(aar, {"classes.jar": classes.read_bytes()})
            contents = aar.read_bytes()
            wrong = directory.parent / "wrong-location.module"
            wrong.write_text(json.dumps({"variants": [{"files": [{
                "name": aar.name,
                "url": aar.name,
                "size": len(contents),
                **{
                    algorithm: hashlib.new(algorithm, contents).hexdigest()
                    for algorithm in ("md5", "sha1", "sha256", "sha512")
                },
            }]}]}) + "\n", encoding="utf-8")
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(b'{"schemaVersion":1}\n')
            with self.assertRaisesRegex(ValueError, "exact owning Gradle module"):
                package_sdk_maven(
                    source, root / "output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )

            exact_module = directory / f"{artifact}-{version}.module"
            exact_module.write_bytes(wrong.read_bytes())
            duplicate_directory = directory.parent / "0-duplicate"
            duplicate_aar = duplicate_directory / aar.name
            _zip(duplicate_aar, {"classes.jar": classes.read_bytes()})
            (duplicate_directory / exact_module.name).write_bytes(wrong.read_bytes())
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                package_sdk_maven(
                    source, root / "ambiguous-output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )

            shutil.rmtree(duplicate_directory)
            exact_module.write_text(json.dumps({
                "variants": [],
                "decoy": json.loads(wrong.read_text(encoding="utf-8"))["variants"][0]["files"][0],
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "absent from its exact Gradle module"):
                package_sdk_maven(
                    source, root / "decoy-output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )


if __name__ == "__main__":
    unittest.main()
