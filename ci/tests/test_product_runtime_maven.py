"""Synthetic Maven content fixtures; not compiler, host or signed admission."""
import copy
import hashlib
import unittest

from ci.products.contract_model import (
    CONTRACT_CHECKSUM_SUFFIXES, CONTRACT_VARIANT_PREFIXES,
    _contract_expected_variant_attributes, _contract_target_variant_roles,
)
from ci.products.inventory import canonical_json_bytes, load_json_bytes, sha256_bytes
from ci.products.runtime_maven import (
    COMPONENTS, GROUP, _CORE, _suffixes, validate_runtime_maven_publications,
)


def runtime_maven_fixture(runtime_version="0.2.9", contract_version="0.2.0", *, original_primaries=None):
    """All eight publication shapes with visibly synthetic original binaries."""
    contents = {}
    for component in COMPONENTS:
        core = _CORE[component]
        suffix = core.removeprefix("codex-agent-core-")
        artifact = "codex-agent-runtime-desktop-" + suffix
        stem = artifact + "-" + runtime_version
        directory = f"maven/{component}/{GROUP.replace('.', '/')}/{artifact}/{runtime_version}/"
        primaries = {stem + value: f"synthetic {component} {value}\n".encode()
                     for value in _suffixes(component)}
        if original_primaries is not None:
            expected = {"main.jar" if component == "jvm" else "main.klib", "sources.jar", "javadoc.jar"}
            if component not in {"jvm", "node-js", "node-wasm"}:
                expected |= {"cinterop-codexDesktop.klib", "cinterop-codexAgentC.klib"}
            if component in {"macos-arm64", "macos-x64"}:
                expected.add("metadata.jar")
            supplied = original_primaries[component]
            if set(supplied) != expected or any(type(value) is not bytes or not value for value in supplied.values()):
                raise ValueError("Synthetic fixture requires the exact nonempty original primary inventory")
            for name, value in supplied.items():
                published_suffix = name.removeprefix("main") if name.startswith("main.") else "-" + name
                primaries[stem + published_suffix] = value
        dependencies = {
            (GROUP, "codex-agent-core"): contract_version,
            ("org.jetbrains.kotlin", "kotlin-stdlib"): "2.3.10",
            ("org.jetbrains.kotlinx", "kotlinx-coroutines-core"): "1.10.2",
            ("com.squareup.okio", "okio"): "3.16.2",
        }
        if component == "node-js":
            dependencies["org.jetbrains.kotlin", "kotlin-dom-api-compat"] = "2.3.10"
        pom_dependencies = []
        for (group, module), version in dependencies.items():
            name = core if group == GROUP else module
            if module in {"kotlinx-coroutines-core", "okio"} or (
                module == "kotlin-stdlib" and component in {"node-js", "node-wasm"}
            ):
                name += "-" + suffix
            scope = "runtime" if component in {"jvm", "node-js", "node-wasm"} and module in {
                "kotlinx-coroutines-core", "okio"
            } else "compile"
            pom_dependencies.append(f"<dependency><groupId>{group}</groupId><artifactId>{name}</artifactId>"
                                    f"<version>{version}</version><scope>{scope}</scope></dependency>")
        primaries[stem + ".pom"] = (
            '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
            f"<groupId>{GROUP}</groupId><artifactId>{artifact}</artifactId><version>{runtime_version}</version>"
            f"<packaging>{'jar' if component == 'jvm' else 'klib'}</packaging>"
            f"<dependencies>{''.join(pom_dependencies)}</dependencies></project>"
        ).encode()
        variants = []
        roles = _contract_target_variant_roles(core)
        role_order = (["api", "runtime", "sources"] if "runtime" in roles else
                      ["api", "sources", "metadata"] if "metadata" in roles else ["api", "sources"])
        prefix = CONTRACT_VARIANT_PREFIXES[core]
        title = {"node-js": "NodeJs", "node-wasm": "NodeWasm"}.get(component, prefix[0].upper() + prefix[1:])
        for index, role in enumerate(role_order):
            filename = stem + ("-sources.jar" if role == "sources" else "-metadata.jar" if role == "metadata"
                               else ".jar" if component == "jvm" else ".klib")
            filenames = [filename]
            if component not in {"jvm", "node-js", "node-wasm"} and role == "api":
                filenames += [stem + "-cinterop-codexDesktop.klib", stem + "-cinterop-codexAgentC.klib"]
            values = {} if role == "sources" else dependencies
            if component in {"jvm", "node-js", "node-wasm"} and role == "api":
                values = {key: value for key, value in values.items() if key[0] in {GROUP, "org.jetbrains.kotlin"}}
            variants.append({
                "name": f"imported{title}RuntimeVariant{index}",
                "attributes": _contract_expected_variant_attributes(core, role),
                **({"dependencies": [{"group": group, "module": module, "version": {"requires": version}}
                                     for (group, module), version in values.items()]} if values else {}),
                "files": [{"name": name, "url": name, "size": len(primaries[name]),
                           **{algorithm: hashlib.new(algorithm, primaries[name]).hexdigest()
                              for algorithm in ("md5", "sha1", "sha256", "sha512")}} for name in filenames],
            })
        primaries[stem + ".module"] = canonical_json_bytes({
            "formatVersion": "1.1", "component": {"group": GROUP, "module": artifact, "version": runtime_version,
                                                   "attributes": {"org.gradle.status": "release"}},
            "createdBy": {"gradle": {"version": "9.4.1"}}, "variants": variants,
        })
        for name, value in primaries.items():
            contents[directory + name] = value
    return refreshed(contents)


def refreshed(contents):
    """Reframe mutations so semantic negatives cannot pass via checksum failure."""
    contents = {path: value for path, value in contents.items()
                if not any(path.endswith(suffix) for suffix in CONTRACT_CHECKSUM_SUFFIXES)}
    records = []
    for path, value in list(contents.items()):
        for suffix in CONTRACT_CHECKSUM_SUFFIXES:
            contents[path + suffix] = hashlib.new(suffix[1:], value).hexdigest().encode() + b"\n"
    for path, value in sorted(contents.items()):
        component = path.split("/")[1]
        role = ("checksum" if any(path.endswith(suffix) for suffix in CONTRACT_CHECKSUM_SUFFIXES) else
                "sources" if path.endswith("-sources.jar") else "javadoc" if path.endswith("-javadoc.jar") else
                "module-metadata" if path.endswith((".pom", ".module")) else "runtime-resolution")
        records.append({"path": path, "component": component, "role": role,
                        "bytes": len(value), "sha256": sha256_bytes(value)})
    return records, contents


class RuntimeMavenPublicationsTest(unittest.TestCase):
    def setUp(self):
        self.records, self.contents = runtime_maven_fixture()
        self.before = copy.deepcopy((self.records, self.contents))

    def verify(self, records=None, contents=None):
        return validate_runtime_maven_publications("0.2.9", "0.2.0",
                                                  self.records if records is None else records,
                                                  self.contents if contents is None else contents)

    def path(self, component, suffix):
        return next(path for path in self.contents if path.startswith("maven/" + component + "/") and path.endswith(suffix))

    def mutated_module(self, component, mutate):
        contents = dict(self.contents)
        path = self.path(component, ".module")
        module = load_json_bytes(contents[path])
        mutate(module)
        contents[path] = canonical_json_bytes(module)
        return refreshed(contents)

    def test_exact_eight_publications_preserve_original_bytes_and_separate_versions(self):
        self.assertIsNone(self.verify())
        self.assertEqual(self.before, (self.records, self.contents))
        self.assertEqual(260, len(self.records))
        for version in ("0.2.0", "0.2.1", "1.0.0-rc.1"):
            records, contents = runtime_maven_fixture(version, "0.1.9")
            validate_runtime_maven_publications(version, "0.1.9", records, contents)

    def test_missing_extra_cross_target_and_noncanonical_role_inventory(self):
        for component, suffix in (("macos-arm64", "-metadata.jar"), ("windows-x64", "-cinterop-codexAgentC.klib"),
                                  ("jvm", ".pom"), ("node-wasm", "-sources.jar")):
            contents = dict(self.contents)
            del contents[self.path(component, suffix)]
            with self.subTest(component=component), self.assertRaisesRegex(ValueError, "inventory"):
                self.verify(*refreshed(contents))
        for component, suffix in (("linux-x64", "-metadata.jar"), ("jvm", ".asc"), ("node-js", ".extra")):
            contents = dict(self.contents)
            contents[self.path(component, ".pom").removesuffix(".pom") + suffix] = b"extra\n"
            with self.subTest(component=component), self.assertRaises(ValueError):
                self.verify(*refreshed(contents))
        for field, value in (("component", "node-js"), ("role", "runtime-resolution")):
            records = copy.deepcopy(self.records)
            next(record for record in records if record["path"] == self.path("jvm", ".pom"))[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(records=records)

    def test_pom_contract_target_version_duplicate_and_resolution_override_reject(self):
        path = self.path("macos-arm64", ".pom")
        original = self.contents[path]
        mutations = [original.replace(b"codex-agent-core-macosarm64", b"codex-agent-core-linuxx64"),
                     original.replace(b"<version>0.2.0</version>", b"<version>0.2.1</version>"),
                     original.replace(b"</dependencies>", b"<dependency><groupId>io.github.codex-agent-labs</groupId>"
                                      b"<artifactId>codex-agent-core-macosarm64</artifactId><version>0.2.0</version>"
                                      b"</dependency></dependencies>"),
                     original.replace(b"</project>", b"<profiles/></project>"),
                     original.replace(b"<scope>compile</scope>", b"<scope>runtime</scope>"),
                     b'<!DOCTYPE project [<!ENTITY x "bad">]>' + original]
        for mutation in mutations:
            contents = dict(self.contents)
            contents[path] = mutation
            with self.subTest(mutation=mutation[:80]), self.assertRaises(ValueError):
                self.verify(*refreshed(contents))

    def test_gmm_target_contract_duplicate_roles_and_file_binding_reject(self):
        def contract(module):
            module["variants"][0]["dependencies"][0]["version"]["requires"] = "0.2.1"

        mutations = [
            lambda module: module["component"].update(version="0.2.0"), contract,
            lambda module: module["variants"].append(copy.deepcopy(module["variants"][0])),
            lambda module: module["variants"][0]["attributes"].update({"org.jetbrains.kotlin.native.target": "linux_x64"}),
            lambda module: module["variants"][0]["files"][0].update(url="../original.klib"),
            lambda module: module["variants"][0]["files"][0].update(sha256="0" * 64),
            lambda module: module["variants"][0]["files"][0].update(size=True),
            lambda module: module["variants"][0].update(**{"available-at": {"url": "other.module"}}),
            lambda module: module["createdBy"]["gradle"].update(buildId="execution-identity"),
            lambda module: module["variants"][0]["dependencies"].pop(),
            lambda module: module["variants"].reverse(),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.verify(*self.mutated_module("macos-arm64", mutate))

    def test_native_cinterops_must_remain_in_actual_kgp_api_usage(self):
        def remove_from_usage(module):
            module["variants"][0]["files"] = [record for record in module["variants"][0]["files"]
                                               if "-cinterop-" not in record["name"]]
        for component in ("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"):
            with self.subTest(component=component), self.assertRaisesRegex(ValueError, "primary/cinterop inventory"):
                self.verify(*self.mutated_module(component, remove_from_usage))

    def test_native_implementation_compile_scope_and_cross_view_versions_are_bound(self):
        contents = dict(self.contents)
        path = self.path("linux-arm64", ".pom")
        old = b"<scope>compile</scope></dependency></dependencies>"
        self.assertIn(old, contents[path])
        contents[path] = contents[path].replace(old, b"<scope>runtime</scope></dependency></dependencies>")
        with self.assertRaisesRegex(ValueError, "scope/type/exclusions"):
            self.verify(*refreshed(contents))

        def change_okio(module):
            dependency = next(item for item in module["variants"][0]["dependencies"] if item["module"] == "okio")
            dependency["version"]["requires"] = "3.16.3"
        with self.assertRaisesRegex(ValueError, "versions disagree"):
            self.verify(*self.mutated_module("linux-arm64", change_okio))

    def test_checksum_and_duplicate_json_keys_fail_without_rewriting_originals(self):
        contents = dict(self.contents)
        path = self.path("node-js", ".pom.sha256")
        contents[path] = contents[path].rstrip(b"\n")
        with self.assertRaises(ValueError):
            self.verify(contents=contents)
        contents = dict(self.contents)
        path = self.path("node-js", ".module")
        contents[path] = contents[path].replace(b'"formatVersion":"1.1"', b'"formatVersion":"1.1","formatVersion":"1.1"')
        with self.assertRaises(ValueError):
            self.verify(*refreshed(contents))
        self.assertEqual(self.before, (self.records, self.contents))


if __name__ == "__main__":
    unittest.main()
