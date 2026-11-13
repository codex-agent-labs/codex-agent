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
    needs[parent]["outputs"].update(locator() if state is None else state)
    if state == {} and parent == election:
        needs[parent]["outputs"].pop("sdk_workers_required")
    if stage == "package":
        needs[election]["outputs"]["preparation_required"] = str(preparation).lower()
        needs["sdk-native-prepare"] = job("success" if preparation else "skipped")
    if stage == "ios-validation":
        needs["plan"] = job("success", native_ios_worker_ready="false")
        needs["sdk-ios-validation-native"] = job()
        for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation"):
            needs[name] = job("success" if required else "skipped")
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
    def test_retained_signing_route_still_requires_complete_successful_collection(self):
        needs = needs_for("ios-validation", required=True)
        needs["sdk-ios-validation-outcome"] = job("success", signing_required="false", all_failed="false")
        for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation"):
            needs[name] = job()
        self.assertEqual("9", routing.select_native_state(needs, stage="ios-validation")["sdk_state_wave"])
        for failure in ("outcome", "missing", "all-failed", "signer", "collector", "wave-failed"):
            changed = deepcopy(needs)
            if failure == "outcome": changed["sdk-ios-validation-outcome"]["result"] = "failure"
            elif failure == "missing": del changed["sdk-ios-validation-outcome"]["outputs"]["signing_required"]
            elif failure == "all-failed": changed["sdk-ios-validation-outcome"]["outputs"]["all_failed"] = "true"
            elif failure == "signer": changed["sdk-apple-validation-attestation"]["result"] = "failure"
            elif failure == "collector": changed["sdk-collect-9"]["result"] = "failure"
            else: changed["sdk-collect-9"]["outputs"]["wave_failed"] = "true"
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                routing.select_native_state(changed, stage="ios-validation")

    def test_core_android_continuation_has_exact_eight_wave_chain(self):
        families = ("core-binary", "core-package", "core-validation", "core-metadata",
                    "android-binary", "android-package", "android-validation", "android-metadata")
        parent = "sdk-ios-metadata-result"
        for wave, family in enumerate(families, start=11):
            expected = (parent, f"sdk-{family}-plan", f"sdk-{family}", f"sdk-collect-{wave}", str(wave))
            self.assertEqual(expected, routing._STAGES[family])
            for required in (False, True):
                current = locator(str(wave - 1), "0")
                selected = needs_for(family, required=required, state=current)
                self.assertEqual((dict(artifact_id="456", artifact_digest="sha256:" + "b" * 64,
                    state_wave="0", sdk_state_wave=str(wave)) if required else current),
                    routing.select_native_state(selected, stage=family))
            parent = ("sdk-core-binary-wave" if family == "core-binary" else
                      "sdk-core-package-wave" if family == "core-package" else
                      "sdk-core-validation-wave" if family == "core-validation" else
                      "sdk-core-metadata-wave" if family == "core-metadata" else f"sdk-{family}-result")
        stale = needs_for("core-package", required=True, state=locator("11", "0"))
        stale["sdk-core-binary-result"] = stale.pop("sdk-core-binary-wave")
        with self.assertRaises(ValueError):
            routing.select_native_state(stale, stage="core-package")
        stale = needs_for("core-validation", required=True, state=locator("12", "0"))
        stale["sdk-core-package-result"] = stale.pop("sdk-core-package-wave")
        with self.assertRaises(ValueError):
            routing.select_native_state(stale, stage="core-validation")
        self.assertEqual(("sdk-javascript-metadata-result", "sdk-csharp-binary-plan", "sdk-csharp-binary", "sdk-collect-19", "19"),
                         routing._STAGES["csharp-binary"])
        for required in (False, True):
            selected = needs_for("csharp-binary", required=required, state=locator("2", "0"))
            self.assertEqual((locator("19", "0") | {"artifact_id": "456", "artifact_digest": "sha256:" + "b" * 64})
                             if required else locator("2", "0"),
                             routing.select_native_state(selected, stage="csharp-binary"))
        for invalid in ("20", "0", "01", "-1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                routing._locator(locator(invalid, "0"))

    def test_ios_metadata_exact_terminal_route_and_unchanged_validation_parent(self):
        self.assertEqual(("sdk-ios-validation-result", "sdk-ios-metadata-plan", "sdk-ios-metadata", "sdk-collect-10", "10"),
                         routing._STAGES["ios-metadata"])
        for parent in (locator("9", "0"), locator("8", "0"), locator("", "3")):
            for required in (False, True):
                needs = needs_for("ios-metadata", required=required, state=parent)
                before = deepcopy(needs)
                with self.subTest(parent=parent, required=required):
                    self.assertEqual(dict(artifact_id="456", artifact_digest="sha256:" + "b" * 64,
                                          state_wave="0", sdk_state_wave="10") if required else parent,
                                     routing.select_native_state(needs, stage="ios-metadata"))
                    self.assertEqual(before, needs)
                    changed = deepcopy(needs)
                    changed["sdk-native-result"] = changed.pop("sdk-ios-validation-result")
                    with self.assertRaises(ValueError):
                        routing.select_native_state(changed, stage="ios-metadata")

    def test_native_ios_worker_requires_exclusive_election_and_unchanged_original_parent(self):
        state = locator("", "0")
        needs = needs_for("ios-validation", required=True, state=state)
        matrix = '{"include":[{"target":"ios-arm64","buildKey":"sha256:' + 'c' * 64 + '"}]}'
        needs["plan"]["outputs"] = dict(native_ios_worker_ready="true", native_ios_matrix=matrix,
            native_resume_artifact_id=state["artifact_id"], native_resume_artifact_digest=state["artifact_digest"])
        needs["sdk-native-result"]["outputs"]["sdk_matrix"] = matrix
        needs["sdk-ios-validation"] = job()
        needs["sdk-ios-validation-native"] = job("success")
        before = deepcopy(needs)
        self.assertEqual("9", routing.select_native_state(needs, stage="ios-validation")["sdk_state_wave"])
        self.assertEqual(before, needs)
        for name in ("plan", "sdk-ios-validation-native", "sdk-apple-signing-prepare",
                     "sdk-apple-validation-attestation", "sdk-collect-9"):
            for status in ("skipped", "failure", "cancelled"):
                changed = deepcopy(needs)
                changed[name]["result"] = status
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    routing.select_native_state(changed, stage="ios-validation")
        for name, key, value in (
            ("plan", "native_ios_worker_ready", "false"), ("plan", "native_ios_worker_ready", True),
            ("plan", "native_resume_artifact_id", "999"),
            ("plan", "native_resume_artifact_digest", "sha256:" + "d" * 64),
            ("plan", "native_ios_matrix", ""), ("plan", "native_ios_matrix", '{"include":[]}'),
            ("sdk-native-result", "sdk_matrix", '{"include":[]}'),
            ("sdk-native-result", "sdk_workers_required", "false"),
            ("sdk-native-result", "sdk_state_wave", "8"), ("sdk-collect-9", "wave_failed", "true")):
            changed = deepcopy(needs)
            changed[name]["outputs"][key] = value
            with self.subTest(name=name, key=key), self.assertRaises(ValueError):
                routing.select_native_state(changed, stage="ios-validation")
        for status in ("success", "failure", "cancelled"):
            changed = deepcopy(needs)
            changed["sdk-ios-validation"]["result"] = status
            with self.subTest(ordinary=status), self.assertRaises(ValueError):
                routing.select_native_state(changed, stage="ios-validation")
        ordinary = needs_for("ios-validation", required=True, state=state)
        for status in ("success", "failure", "cancelled"):
            changed = deepcopy(ordinary)
            changed["sdk-ios-validation-native"]["result"] = status
            with self.subTest(unelected_native=status), self.assertRaises(ValueError):
                routing.select_native_state(changed, stage="ios-validation")
        for name in ("plan", "sdk-ios-validation-native"):
            changed = deepcopy(needs)
            del changed[name]
            with self.subTest(missing=name), self.assertRaises(ValueError):
                routing.select_native_state(changed, stage="ios-validation")

    def test_ios_validation_exact_terminal_route_and_all_preparation_signer_gates(self):
        self.assertEqual(("sdk-native-result", "sdk-native-result", "sdk-ios-validation", "sdk-collect-9", "9"),
                         routing._STAGES["ios-validation"])
        parent = locator("8", "0")
        for required in (False, True):
            needs = needs_for("ios-validation", required=required, state=parent)
            before = deepcopy(needs)
            result = routing.select_native_state(needs, stage="ios-validation")
            self.assertEqual(dict(artifact_id="456", artifact_digest="sha256:" + "b" * 64,
                                  state_wave="0", sdk_state_wave="9") if required else parent, result)
            self.assertEqual(before, needs)
            for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation"):
                for status in ("failure", "cancelled", "in_progress", "skipped" if required else "success"):
                    changed = deepcopy(needs)
                    changed[name]["result"] = status
                    with self.subTest(required=required, name=name, status=status), self.assertRaises(ValueError):
                        routing.select_native_state(changed, stage="ios-validation")
                changed = deepcopy(needs)
                del changed[name]
                with self.assertRaises(ValueError):
                    routing.select_native_state(changed, stage="ios-validation")
        changed = needs_for("ios-validation", required=True, state=parent)
        changed["sdk-native-validation-result"] = changed.pop("sdk-native-result")
        with self.assertRaises(ValueError):
            routing.select_native_state(changed, stage="ios-validation")

    def test_ios_package_and_javascript_metadata_use_exact_fixed_parent_and_collector(self):
        routes = (
            ("ios-package", "sdk-native-packages", "sdk-ios-package-plan", "sdk-ios-package", "sdk-collect-5", "5"),
            ("javascript-metadata", "sdk-javascript", "sdk-javascript-metadata-plan", "sdk-javascript-metadata", "sdk-collect-6", "6"),
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
        self.assertEqual("sdk-ios-packages", routing._STAGES["validation"][0])

    def test_javascript_completes_before_csharp_and_packages_without_losing_state(self):
        self.assertEqual('sdk-javascript', routing._STAGES['javascript-metadata'][0])
        for required in (False, True):
            state = locator('2', '0')
            for stage in ('javascript-metadata', 'csharp-binary', 'package', 'ios-package', 'validation'):
                with self.subTest(stage=stage, required=required):
                    needs = needs_for(stage, required=required, preparation=required, state=state)
                    selected = routing.select_native_state(needs, stage=stage)
                    self.assertEqual(routing._STAGES[stage][-1] if required else state['sdk_state_wave'],
                                     selected['sdk_state_wave'])
                    state = selected
        stale = needs_for('validation', required=False, state=state)
        stale['sdk-javascript-metadata-result'] = stale.pop('sdk-ios-packages')
        with self.assertRaises(ValueError):
            routing.select_native_state(stale, stage='validation')

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
        for state in (locator("4", "0"), locator("7", "0"), locator("9", "0"), locator("10", "0"), locator("", "5")):
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
                if name == "plan":
                    continue  # Plan is upstream authorization, not an elected family operation.
                changed = deepcopy(needs)
                changed[name]["result"] = "failure" if name == parent else "success"
                with self.subTest(stage=stage, name=name), self.assertRaises(ValueError):
                    routing.select_native_state(changed, stage=stage)

    def test_combined_ios_election_cannot_run_without_parent(self):
        for value in ("true", "false", True, None):
            needs = needs_for("ios-validation", state={})
            needs["sdk-native-result"]["outputs"]["sdk_workers_required"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "without parent"):
                routing.select_native_state(needs, stage="ios-validation")

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
            for state in (locator("0", "0"), locator("7", "1"), locator("20", "0"), locator("", "6")):
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
