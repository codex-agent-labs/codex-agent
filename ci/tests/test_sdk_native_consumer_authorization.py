"""Local authorization/wiring checks, not genuine product acceptance evidence."""

from unittest import TestCase
from unittest.mock import patch

from ci import native_wrappers
from ci.native_wrappers import require_matching_native, run
from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree, write_canonical_json
from ci.products.sdk_package import consume_authorized_native, verified_native_consumer_authorization
from ci.tests import test_sdk_runtime_root


class NativeConsumerAuthorizationTest(TestCase):
    def setUp(self):
        fixture = self.fixture = test_sdk_runtime_root.SdkRuntimeRootTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        sidecars = fixture.evidence("consumer", runtime_version="0.8.0")
        self.evidence = self.capture(sidecars)
        claim = load_canonical_json_bytes((sidecars / "runtime-library-authorization.json").read_bytes())
        runtime = fixture.compatibility["runtime"]
        runtime["defaultManifestSha256"] = claim["aggregateManifestSha256"]
        variant = next(row for row in runtime["embeddedVariants"] if row["target"] == "macos-arm64")
        variant.update(componentId=claim["runtimeIdentity"]["componentId"],
            bundleSha256=claim["variantBundleSha256"], manifestSha256=claim["variantManifestSha256"],
            runtimeLibrarySha256=claim["runtimeLibrarySha256"])
        self.sdks = fixture.root / "sdks"
        self.library = self.sdks / "macos-arm64/lib/libcodex_agent.dylib"
        self.library.parent.mkdir(parents=True)
        self.library.write_bytes(fixture.library.read_bytes())
        write_canonical_json(self.sdks / "sdk-compatibility.json", fixture.compatibility)
        (self.sdks / "sdk-runtime-root.pub").write_bytes(fixture.root_public.read_bytes())
        self.packages = fixture.root / "packages"
        self.packages.mkdir()
        self.installed = self.packages / "installed.dylib"
        self.installed.write_bytes(self.library.read_bytes())
        self.output = fixture.root / "output"
        self.repository = fixture.root / "repository"
        self.repository.mkdir()

    def capture(self, sidecars):
        root = sidecars.with_name(sidecars.name + "-capture")
        snapshot_regular_tree(sidecars, root / "sidecars")
        # Signature/consumer fixture only; no hosted capture claimed by this test.
        write_canonical_json(root / "transport.json", {"schemaVersion": 1,
            "kind": "sdk-runtime-authorization-capture", "target": "macos-arm64",
            "source": {"unitFixture": True}, "observed": [], "artifact": {},
            "files": regular_file_inventory(sidecars), "rangeBytes": 0, "elapsedNs": 0})
        return root

    def consume(self, consumer, run, language="python"):
        with patch.object(native_wrappers, "_consume", consumer), \
                patch.object(native_wrappers, "host_classifier", return_value="macos-arm64"), \
                patch.object(native_wrappers, "run", run):
            consume_authorized_native(self.repository, self.packages, self.sdks, self.output,
                "0.8.0", language, runtime_authorization=self.evidence,
                expected_classifier="macos-arm64", offline=True)

    @staticmethod
    def consumer(repository, packages, sdks, plan, output, version, **kwargs):
        # This function is rebound into the original consumer's private globals,
        # exercising its real equality/output gates without pretending to compile.
        library = require_matching_native(packages, "installed.dylib",
            sdks / "macos-arm64/lib/libcodex_agent.dylib", "unit fixture")
        run("package-negative")
        run("external-positive", library)
        run("after")
        output.mkdir()
        (output / "unit-only").write_text("not a host receipt")

    def test_exact_signed_default_is_private_and_rotation_does_not_change_sdk_bytes(self):
        before = regular_file_inventory(self.sdks)
        for evidence in (self.evidence, self.capture(self.fixture.evidence("rotated", runtime_version="0.8.0"))):
            with verified_native_consumer_authorization(evidence, self.sdks, "macos-arm64") as captured:
                self.assertNotEqual(captured, evidence)
                self.assertEqual(regular_file_inventory(captured), regular_file_inventory(evidence / "sidecars"))
            self.assertFalse(captured.exists())
            self.assertEqual(before, regular_file_inventory(self.sdks))
        newer = self.capture(self.fixture.evidence("newer", runtime_version="0.8.1"))
        with self.assertRaisesRegex(ValueError, "selected SDK Runtime"):
            with verified_native_consumer_authorization(newer, self.sdks, "macos-arm64"):
                self.fail("compatible external release is not the selected default for this test")

    def test_sidecars_exist_only_for_external_call_and_shared_functions_stay_unchanged(self):
        functions = {name: getattr(native_wrappers, name) for name in ("_consume", "consume_language", "require_matching_native", "run")}
        before = regular_file_inventory(self.packages)
        calls = []
        def run(command, *args, **kwargs):
            calls.append(command)
            sidecar = self.installed.with_name(self.installed.name + ".evidence")
            self.assertEqual(sidecar.exists(), command == "external-positive")
            if sidecar.exists():
                self.assertEqual(regular_file_inventory(sidecar), regular_file_inventory(self.evidence / "sidecars"))
        self.consume(self.consumer, run)
        self.assertEqual(calls, ["package-negative", "external-positive", "after"])
        self.assertTrue(self.output.is_dir())
        self.assertEqual(before, regular_file_inventory(self.packages))
        for name, original in functions.items():
            self.assertIs(getattr(native_wrappers, name), original)

    def test_signature_equality_and_lifetime_failures_clear_output_without_modifying_originals(self):
        for failure in ("signature", "library", "execution", "lifetime"):
            with self.subTest(failure=failure):
                signature = self.evidence / "sidecars/runtime-library-authorization.sig"
                original = signature.read_bytes()
                if failure == "signature":
                    signature.write_bytes(original + b"invalid")
                if failure == "library":
                    self.installed.write_bytes(b"wrong library")
                self.output.mkdir(exist_ok=True)
                (self.output / "stale").write_text("not accepted")
                def run(command, *args, **kwargs):
                    if command == "external-positive":
                        if failure == "execution":
                            raise RuntimeError("external consumer failure")
                        if failure == "lifetime":
                            signature.write_bytes(original + b"changed")
                with self.assertRaises((ValueError, RuntimeError)):
                    self.consume(self.consumer, run)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.installed.with_name(self.installed.name + ".evidence").exists())
                signature.write_bytes(original)
                self.installed.write_bytes(self.library.read_bytes())

    def test_missing_external_execution_is_not_success_and_overlap_preserves_evidence(self):
        def omitted(repository, packages, sdks, plan, output, version, **kwargs):
            output.mkdir()
        with self.assertRaisesRegex(ValueError, "exactly one external-positive"):
            self.consume(omitted, lambda *args, **kwargs: None)
        self.assertFalse(self.output.exists())
        before = regular_file_inventory(self.evidence)
        self.output = self.evidence
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.consume(self.consumer, lambda *args, **kwargs: None)
        self.assertEqual(before, regular_file_inventory(self.evidence))

    def test_only_rust_mock_invocation_routes_to_the_test_only_loader(self):
        def consumer(repository, packages, sdks, plan, output, version, **kwargs):
            library = require_matching_native(packages, "installed.dylib",
                sdks / "macos-arm64/lib/libcodex_agent.dylib", "unit fixture")
            run("external-positive", library)
            run("cargo", "run", "--manifest-path", output.parent / "rust-consumer/Cargo.toml",
                "--release", "--locked", "--offline", "--bin", "codex-agent-rust-lifecycle-smoke", "--",
                output.parent / "mock.dylib", cwd=output.parent, env={"CARGO_TARGET_DIR": str(output.parent / "rust-target")})
            output.mkdir()
        calls = []
        with patch("ci.products.sdk_package.run_rust_fixture_consumer") as fixture:
            self.consume(consumer, lambda *command, **options: calls.append(command), language="rust")
        self.assertEqual([("external-positive", self.installed)], calls)
        fixture.assert_called_once_with(self.installed.parents[2],
            self.output.parent / "rust-consumer/src/bin/lifecycle_smoke.rs", self.output.parent / "mock.dylib",
            environ={"CARGO_TARGET_DIR": str(self.output.parent / "rust-target")})

    def test_dotnet8_restore_keeps_isolated_sources_and_cache_policy(self):
        def consumer(repository, packages, sdks, plan, output, version, **kwargs):
            run("dotnet", "restore", packages / "Consumer.csproj", "--force", "--no-http-cache",
                "--packages", packages / "cache", "--configfile", packages / "NuGet.Config", cwd=packages)
            library = require_matching_native(packages, "installed.dylib",
                sdks / "macos-arm64/lib/libcodex_agent.dylib", "unit fixture")
            run("external-positive", library)
            output.mkdir()
        calls = []
        self.consume(consumer, lambda *command, **options: calls.append((command, options)), language="csharp")
        self.assertEqual((("dotnet", "restore", self.packages / "Consumer.csproj", "--force", "--no-cache",
            "--packages", self.packages / "cache", "--configfile", self.packages / "NuGet.Config"),
            {"cwd": self.packages}), calls[0])
        self.assertEqual(("external-positive", self.installed), calls[1][0])

    def test_all_language_plan_reuses_one_authorization_and_keeps_negative_output(self):
        build = self.repository / "build"
        build.mkdir()
        output, negatives, plan = build / "host", build / "negative", build / "plan.json"
        plan.write_text("fixture plan, no lane acceptance")
        for name in ("Python", "C#", "Rust", "C++", "Dart"):
            path = self.packages / name / "installed.dylib"
            path.parent.mkdir()
            path.write_bytes(self.library.read_bytes())
        repeated = []

        def consumer(repository, packages, sdks, original_plan, destination, version, **kwargs):
            assert original_plan == plan
            assert kwargs["package_negative_evidence"] == negatives
            for name in ("Python", "C#", "Rust", "C++", "Dart"):
                library = require_matching_native(packages / name, "installed.dylib",
                    sdks / "macos-arm64/lib/libcodex_agent.dylib", name)
                run("external-positive", library)
            if repeated:
                run("external-positive", library)
            negatives.mkdir()
            (negatives / "unit-only").write_text("not genuine package-negative evidence")
            destination.mkdir()
            (destination / "unit-only").write_text("not a genuine lane receipt")

        def execute(command, library):
            sidecar = library.with_name(library.name + ".evidence")
            self.assertEqual(regular_file_inventory(sidecar), regular_file_inventory(self.evidence / "sidecars"))

        for reject in (False, True):
            if reject:
                repeated.append(True)
            with patch.object(native_wrappers, "_consume", consumer), \
                    patch.object(native_wrappers, "host_classifier", return_value="macos-arm64"), \
                    patch.object(native_wrappers, "run", execute), \
                    patch("ci.products.sdk_package.verified_native_consumer_authorization",
                          wraps=verified_native_consumer_authorization) as authorization:
                def invoke():
                    consume_authorized_native(self.repository, self.packages, self.sdks, output, "0.8.0", None,
                        runtime_authorization=self.evidence, expected_classifier="macos-arm64",
                        package_negative_evidence=negatives, plan=plan)
                if reject:
                    with self.assertRaisesRegex(ValueError, "repeated an external-positive"):
                        invoke()
                else:
                    invoke()
                authorization.assert_called_once()
                self.assertEqual(output.exists(), not reject)
                self.assertEqual(negatives.exists(), not reject)
                self.assertFalse(list(self.packages.rglob("*.evidence")))
