"""Pure routing fixtures: no state authentication, compiler or hosted proof."""

from copy import deepcopy
import unittest

from ci import sdk_native_continuation as routing
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS


def ready(component="python", phase="package", target="desktop", product="sdk"):
    inventory = [{"relativePath": "fixture.txt", "bytes": 7, "sha256": sha256_bytes(b"fixture")}]
    plan = dict(schemaVersion=1, product=product, component=component, phase=phase, target=target,
        inputs={"inventory": inventory, "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
                "versionIdentity": "0.8.0", "upstreamArtifacts": [],
                "toolchainProfileDigest": sha256_bytes(b"synthetic toolchain"),
                "flagsDigest": sha256_bytes(b"synthetic flags"), "outputSchemaVersion": 1})
    plan["buildKey"] = compute_build_key(**{name: plan[name] for name in
        ("product", "component", "phase", "target", "inputs")})
    return plan


def locator(sdk_wave="", state_wave="3"):
    return dict(artifact_id="123", artifact_digest="sha256:" + "a" * 64,
                state_wave=state_wave, sdk_state_wave=sdk_wave)


def job(result="skipped", **outputs):
    return {"result": result, "outputs": outputs}


def needs_for(stage, *, required=False, preparation=False, state=None):
    parent, election, workers, collector, _ = routing._STAGES[stage]
    needs = {parent: job("success", **(locator() if state is None else state)),
        election: job("success", sdk_workers_required=str(required).lower()),
        workers: job("success" if required else "skipped"),
        collector: job("success" if required else "skipped", artifact_id="456",
                       artifact_digest="sha256:" + "b" * 64, wave_failed="false")}
    if stage == "package":
        needs[election]["outputs"]["preparation_required"] = str(preparation).lower()
        needs["sdk-native-prepare"] = job("success" if preparation else "skipped")
    return needs


class NativePreparationAnchorSelectionTest(unittest.TestCase):
    def test_all_exact_anchors_and_deterministic_phase_priority(self):
        plans = [ready(language, phase, target) for language in NATIVE_BINDINGS
                 for phase, target in (("package", "desktop"), ("metadata", "desktop"),
                                      *(("validation", target) for target in NATIVE_TARGETS))]
        self.assertEqual(35, len(plans))
        for plan in plans:
            with self.subTest(identity=[plan[name] for name in routing._IDENTITY]):
                self.assertEqual(dict(preparation_required=True, component=plan["component"],
                    phase=plan["phase"], target=plan["target"], build_key=plan["buildKey"]),
                    routing.select_preparation_anchor([plan]))
        for phase in ("package", "validation", "metadata"):
            expected = min((plan for plan in plans if plan["phase"] == phase),
                           key=lambda plan: tuple(plan[name] for name in routing._IDENTITY))
            for ordered in (plans, list(reversed(plans))):
                before = deepcopy(ordered)
                selected = routing.select_preparation_anchor(ordered)
                self.assertEqual((phase, expected["component"], expected["target"], expected["buildKey"]),
                    tuple(selected[name] for name in ("phase", "component", "target", "build_key")))
                self.assertEqual(before, ordered)
            plans = [plan for plan in plans if plan["phase"] != phase]

    def test_unrelated_plans_ignored_without_inventing_preparation(self):
        unrelated = ready("jvm", "binary", "jvm", "runtime")
        for plans in ([], [unrelated]):
            self.assertEqual(dict(preparation_required=False, component="", phase="", target="", build_key=""),
                             routing.select_preparation_anchor(plans))
        before = deepcopy(unrelated)
        self.assertEqual("python", routing.select_preparation_anchor([unrelated, ready()])["component"])
        self.assertEqual(before, unrelated)

    def test_duplicate_or_malformed_ready_plans_fail_closed(self):
        for plan in (ready(), ready("jvm", "binary", "jvm", "runtime")):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                routing.select_preparation_anchor([plan, deepcopy(plan)])
            for changes in ({"buildKey": "sha256:" + "f" * 64}, {"schemaVersion": True},
                            {"unexpected": True}, {"component": []}, {"inputs": {}},
                            {"phase": "unknown"}, {"target": "unknown"}):
                with self.subTest(changes=changes):
                    with self.assertRaises(ValueError):
                        routing.select_preparation_anchor([{**deepcopy(plan), **changes}])
        with self.assertRaises(ValueError):
            routing.select_preparation_anchor({})


class NativeStateSelectionTest(unittest.TestCase):
    def test_ios_package_and_javascript_metadata_use_exact_fixed_parent_and_collector(self):
        routes = (
            ("ios-package", "sdk-native-packages", "sdk-ios-package-plan", "sdk-ios-package", "sdk-collect-5", "5"),
            ("javascript-metadata", "sdk-native-packages", "sdk-javascript-metadata-plan", "sdk-javascript-metadata", "sdk-collect-6", "6"),
        )
        for stage, parent, election, workers, collector, wave in routes:
            for required in (False, True):
                with self.subTest(stage=stage, required=required):
                    original = locator("4", "0")
                    needs = {
                        parent: job("success", **original),
                        election: job("success", sdk_workers_required=str(required).lower()),
                        workers: job("success" if required else "skipped"),
                        collector: job("success" if required else "skipped", artifact_id="987",
                            artifact_digest="sha256:" + "c" * 64, wave_failed="false"),
                    }
                    before = deepcopy(needs)
                    expected = dict(artifact_id="987", artifact_digest="sha256:" + "c" * 64,
                                    state_wave="0", sdk_state_wave=wave) if required else original
                    self.assertEqual(expected, routing.select_native_state(needs, stage=stage))
                    self.assertEqual(before, needs)
                    changed = deepcopy(needs)
                    changed["unrelated-original-parent"] = changed.pop(parent)
                    with self.assertRaises(ValueError):
                        routing.select_native_state(changed, stage=stage)
        self.assertEqual("sdk-javascript-metadata-result", routing._STAGES["validation"][0])

    def test_javascript_then_native_validation_preserves_collected_or_reused_state(self):
        for javascript_required in (False, True):
            for validation_required in (False, True):
                with self.subTest(javascript=javascript_required, validation=validation_required):
                    parent = locator("4", "0")
                    javascript = needs_for("javascript-metadata", required=javascript_required, state=parent)
                    self.assertIn("sdk-native-packages", javascript)
                    self.assertNotIn("sdk-ios-packages", javascript)
                    selected = routing.select_native_state(javascript, stage="javascript-metadata")
                    self.assertEqual("6" if javascript_required else "4", selected["sdk_state_wave"])
                    validation = needs_for("validation", required=validation_required, state=selected)
                    self.assertIn("sdk-javascript-metadata-result", validation)
                    self.assertNotIn("sdk-native-packages", validation)
                    result = routing.select_native_state(validation, stage="validation")
                    if validation_required:
                        self.assertEqual("7", result["sdk_state_wave"])
                    else:
                        self.assertEqual(selected, result)
                    stale = deepcopy(validation)
                    stale["sdk-native-packages"] = stale.pop("sdk-javascript-metadata-result")
                    with self.assertRaises(ValueError):
                        routing.select_native_state(stale, stage="validation")

    def test_collected_exact_stage_waves_and_unchanged_parent_on_reuse(self):
        for stage, (_, _, _, collector, wave) in routing._STAGES.items():
            for required in (False, True):
                with self.subTest(stage=stage, required=required):
                    needs = needs_for(stage, required=required, preparation=required)
                    before = deepcopy(needs)
                    selected = routing.select_native_state(needs, stage=stage)
                    expected = locator() if not required else dict(
                        artifact_id=needs[collector]["outputs"]["artifact_id"],
                        artifact_digest=needs[collector]["outputs"]["artifact_digest"],
                        state_wave="0", sdk_state_wave=wave)
                    self.assertEqual(expected, selected)
                    self.assertEqual(before, needs)
        for state in (locator("4", "0"), locator("7", "0"), locator("", "5")):
            self.assertEqual(state, routing.select_native_state(needs_for("metadata", state=state), stage="metadata"))

    def test_reused_packages_still_require_independent_preparation_when_elected(self):
        needs = needs_for("package", preparation=True)
        self.assertEqual(locator(), routing.select_native_state(needs, stage="package"))
        for result in ("skipped", "failure", "cancelled"):
            changed = deepcopy(needs)
            changed["sdk-native-prepare"]["result"] = result
            with self.assertRaises(ValueError):
                routing.select_native_state(changed, stage="package")
        for needs in (needs_for("package", required=True), needs_for("package", preparation=False)):
            if not needs["sdk-native-plan"]["outputs"]["sdk_workers_required"] == "true":
                needs["sdk-native-prepare"]["result"] = "success"
            with self.assertRaises(ValueError):
                routing.select_native_state(needs, stage="package")

    def test_absent_parent_requires_every_family_job_skipped(self):
        empty = dict.fromkeys(routing._LOCATOR, "")
        for stage, (parent, _, _, _, _) in routing._STAGES.items():
            needs = needs_for(stage, state={})
            for name in needs:
                if name != parent:
                    needs[name] = job()
            self.assertEqual(empty, routing.select_native_state(needs, stage=stage))
            for name in needs:
                changed = deepcopy(needs)
                changed[name]["result"] = "failure" if name == parent else "success"
                with self.subTest(stage=stage, name=name), self.assertRaises(ValueError):
                    routing.select_native_state(changed, stage=stage)

    def test_failed_siblings_never_pass_even_after_successful_collection(self):
        for stage, (parent, election, workers, collector, _) in routing._STAGES.items():
            needs = needs_for(stage, required=True, preparation=True)
            for name in (parent, election, workers, collector):
                for result in ("failure", "cancelled", "skipped", "in_progress"):
                    changed = deepcopy(needs)
                    changed[name]["result"] = result
                    with self.subTest(stage=stage, name=name, result=result), self.assertRaises(ValueError):
                        routing.select_native_state(changed, stage=stage)
                    self.assertEqual("false", changed[collector]["outputs"]["wave_failed"])
            for field, values in (("wave_failed", ("true", "", False, None)),):
                for value in values:
                    changed = deepcopy(needs)
                    changed[collector]["outputs"][field] = value
                    with self.assertRaises(ValueError):
                        routing.select_native_state(changed, stage=stage)
            for value in ("", True, None):
                changed = deepcopy(needs)
                changed[election]["outputs"]["sdk_workers_required"] = value
                with self.assertRaises(ValueError):
                    routing.select_native_state(changed, stage=stage)

    def test_invalid_partial_locator_and_unelected_workers_fail(self):
        for stage, (parent, _, workers, collector, _) in routing._STAGES.items():
            for name in (parent, collector):
                for field, value in (("artifact_id", "0"), ("artifact_id", 123),
                                     ("artifact_digest", "sha256:" + "A" * 64), ("artifact_id", "")):
                    needs = needs_for(stage, required=True, preparation=True)
                    needs[name]["outputs"][field] = value
                    with self.subTest(stage=stage, name=name, field=field), self.assertRaises(ValueError):
                        routing.select_native_state(needs, stage=stage)
            for state in (locator("0", "0"), locator("7", "1"), locator("9", "0"), locator("", "6")):
                with self.assertRaises(ValueError):
                    routing.select_native_state(needs_for(stage, state=state), stage=stage)
            for name in (workers, collector):
                needs = needs_for(stage)
                needs[name]["result"] = "success"
                with self.assertRaises(ValueError):
                    routing.select_native_state(needs, stage=stage)
        for stage in ("unknown", [], None):
            with self.assertRaises(ValueError):
                routing.select_native_state({}, stage=stage)


if __name__ == "__main__":
    unittest.main()
