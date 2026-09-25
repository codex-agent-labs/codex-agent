"""Pure workflow-output routing, not upload authentication or SDK acceptance."""

from copy import deepcopy
import unittest

from ci import sdk_completion_state as state


def job(result="skipped", **outputs):
    return {"result": result, "outputs": outputs}


def locator(artifact="71", runtime="0", sdk=""):
    return {"artifact_id": artifact, "artifact_digest": "sha256:" + "a" * 64,
            "state_wave": runtime, "sdk_state_wave": sdk}


def needs():
    result = {name: job() for name in state._JOBS}
    result["product-resume"] = job("success", artifact_id="71", artifact_digest="sha256:" + "a" * 64,
                                  wave_failed="false", full_reuse="false")
    result["runtime-continuation"] = job("success", **locator(), sdk_handoff_required="false",
                                         aggregate_state="not-selected", aggregate_required="false")
    result["sdk-ios-binary-plan"] = job("success", sdk_workers_required="false")
    result["sdk-native-result"] = job("success")
    result["sdk-ios-validation-result"] = job("success")
    result["sdk-ios-metadata-result"] = job("success")
    return result


def handoff():
    value = needs()
    value["runtime-continuation"]["outputs"]["sdk_handoff_required"] = "true"
    value["sdk-plan"] = job("success", **locator(), sdk_workers_required="false")
    value["sdk-native-result"] = job("success", **locator("88", sdk="8"))
    value["sdk-ios-validation-result"] = job("success", **locator("88", sdk="8"))
    value["sdk-ios-metadata-result"] = job("success", **locator("88", sdk="8"))
    value["sdk-core-binary-wave"] = job("success", **locator("88", sdk="8"))
    value["sdk-core-package-wave"] = job("success", **locator("88", sdk="8"))
    value["sdk-core-validation-result"] = job("success", **locator("88", sdk="8"))
    value["sdk-core-metadata-result"] = job("success", **locator("88", sdk="8"))
    for name in ("sdk-android-binary-result", "sdk-android-package-result",
                 "sdk-android-validation-result", "sdk-android-metadata-result"):
        value[name] = job("success", **locator("88", sdk="8"))
    return value


def forward_android(value):
    """Model unchanged Android gates after a predecessor-only test edit."""
    for name in ("sdk-android-binary-result", "sdk-android-package-result",
                 "sdk-android-validation-result", "sdk-android-metadata-result"):
        value[name]["outputs"] = deepcopy(value["sdk-core-metadata-result"]["outputs"])
    return value


class SdkCompletionStateTest(unittest.TestCase):
    def test_final_native_state_is_preserved_without_mutating_any_original_outputs(self):
        for runtime, sdk in (("0", "8"), ("0", "7"), ("0", "6"), ("0", "4"), ("0", "3"), ("2", "")):
            value = handoff()
            value["sdk-native-result"]["outputs"] = locator("88", runtime, sdk)
            value["sdk-ios-validation-result"]["outputs"] = locator("88", runtime, sdk)
            value["sdk-ios-metadata-result"]["outputs"] = locator("88", runtime, sdk)
            value["sdk-core-binary-wave"]["outputs"] = locator("88", runtime, sdk)
            value["sdk-core-package-wave"]["outputs"] = locator("88", runtime, sdk)
            value["sdk-core-validation-result"]["outputs"] = locator("88", runtime, sdk)
            value["sdk-core-metadata-result"]["outputs"] = locator("88", runtime, sdk)
            forward_android(value)
            before = deepcopy(value)
            with self.subTest(runtime=runtime, sdk=sdk):
                self.assertEqual(value["sdk-native-result"]["outputs"], state.select_sdk_completion_state(value))
                self.assertEqual(before, value)

    def test_completed_apple_wave_nine_wins_only_after_native_and_apple_terminal_success(self):
        value = handoff()
        value["sdk-ios-validation-result"] = job("success", **locator("99", sdk="9"))
        value["sdk-ios-metadata-result"] = job("success", **locator("99", sdk="9"))
        value["sdk-core-binary-wave"] = job("success", **locator("99", sdk="9"))
        value["sdk-core-package-wave"] = job("success", **locator("99", sdk="9"))
        value["sdk-core-validation-result"] = job("success", **locator("99", sdk="9"))
        value["sdk-core-metadata-result"] = job("success", **locator("99", sdk="9"))
        forward_android(value)
        before = deepcopy(value)
        self.assertEqual(locator("99", sdk="9"), state.select_sdk_completion_state(value))
        self.assertEqual(before, value)
        for name in ("sdk-native-result", "sdk-ios-validation-result", "sdk-ios-metadata-result"):
            for status in ("failure", "cancelled", "skipped", "in_progress"):
                changed = deepcopy(value)
                changed[name]["result"] = status
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    state.select_sdk_completion_state(changed)
        for final in (locator("99", sdk="8"), locator("99", sdk="7"), locator("99", runtime="5")):
            changed = deepcopy(value)
            changed["sdk-ios-validation-result"]["outputs"] = final
            with self.subTest(final=final), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)

    def test_metadata_wave_ten_is_final_only_after_every_preceding_terminal_gate(self):
        value = handoff()
        value["sdk-ios-validation-result"] = job("success", **locator("99", sdk="9"))
        value["sdk-ios-metadata-result"] = job("success", **locator("110", sdk="10"))
        value["sdk-core-binary-wave"] = job("success", **locator("110", sdk="10"))
        value["sdk-core-package-wave"] = job("success", **locator("110", sdk="10"))
        value["sdk-core-validation-result"] = job("success", **locator("110", sdk="10"))
        value["sdk-core-metadata-result"] = job("success", **locator("110", sdk="10"))
        forward_android(value)
        before = deepcopy(value)
        self.assertEqual(locator("110", sdk="10"), state.select_sdk_completion_state(value))
        self.assertEqual(before, value)
        for name in ("sdk-native-result", "sdk-ios-validation-result", "sdk-ios-metadata-result"):
            for status in ("failure", "cancelled", "skipped", "in_progress"):
                changed = deepcopy(value)
                changed[name]["result"] = status
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    state.select_sdk_completion_state(changed)
        for name, invalid in (("sdk-ios-metadata-result", locator("111", sdk="9")),
                              ("sdk-ios-metadata-result", locator("111", sdk="8")),
                              ("sdk-ios-validation-result", locator("110", sdk="10")),
                              ("sdk-native-result", locator("110", sdk="10")),
                              ("sdk-ios-metadata-result", locator("110", sdk="11"))):
            changed = deepcopy(value)
            changed[name]["outputs"] = invalid
            with self.subTest(name=name, invalid=invalid), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)
        value["sdk-ios-validation-result"]["outputs"] = locator("88", sdk="8")
        self.assertEqual(locator("110", sdk="10"), state.select_sdk_completion_state(value))

    def test_core_binary_wave_eleven_is_selected_only_after_its_terminal_gate(self):
        value = handoff()
        value["sdk-ios-metadata-result"] = job("success", **locator("110", sdk="10"))
        value["sdk-core-binary-wave"] = job("success", **locator("111", sdk="11"))
        value["sdk-core-package-wave"] = job("success", **locator("111", sdk="11"))
        value["sdk-core-validation-result"] = job("success", **locator("111", sdk="11"))
        value["sdk-core-metadata-result"] = job("success", **locator("111", sdk="11"))
        forward_android(value)
        self.assertEqual(locator("111", sdk="11"), state.select_sdk_completion_state(value))
        for status in ("failure", "cancelled", "skipped", "in_progress"):
            changed = deepcopy(value)
            changed["sdk-core-binary-wave"]["result"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)
        changed = deepcopy(value)
        changed["sdk-core-binary-wave"]["outputs"] = locator("111", sdk="12")
        with self.assertRaises(ValueError):
            state.select_sdk_completion_state(changed)

    def test_core_package_wave_twelve_requires_its_terminal_gate(self):
        value = handoff()
        value["sdk-core-binary-wave"] = job("success", **locator("111", sdk="11"))
        value["sdk-core-package-wave"] = job("success", **locator("112", sdk="12"))
        value["sdk-core-validation-result"] = job("success", **locator("112", sdk="12"))
        value["sdk-core-metadata-result"] = job("success", **locator("112", sdk="12"))
        forward_android(value)
        self.assertEqual(locator("112", sdk="12"), state.select_sdk_completion_state(value))
        for status in ("failure", "cancelled", "skipped", "in_progress"):
            changed = deepcopy(value)
            changed["sdk-core-package-wave"]["result"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)
        for invalid in (locator("112", sdk="11"), locator("112", sdk="13")):
            changed = deepcopy(value)
            changed["sdk-core-package-wave"]["outputs"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)

    def test_core_validation_wave_thirteen_requires_its_terminal_gate(self):
        value = handoff()
        value["sdk-core-package-wave"] = job("success", **locator("112", sdk="12"))
        value["sdk-core-validation-result"] = job("success", **locator("113", sdk="13"))
        value["sdk-core-metadata-result"] = job("success", **locator("113", sdk="13"))
        forward_android(value)
        self.assertEqual(locator("113", sdk="13"), state.select_sdk_completion_state(value))
        for status in ("failure", "cancelled", "skipped", "in_progress"):
            changed = deepcopy(value)
            changed["sdk-core-validation-result"]["result"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)
        for invalid in (locator("113", sdk="12"), locator("113", sdk="14")):
            changed = deepcopy(value)
            changed["sdk-core-validation-result"]["outputs"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)

    def test_core_metadata_wave_fourteen_requires_its_terminal_gate(self):
        value = handoff()
        value["sdk-core-validation-result"] = job("success", **locator("113", sdk="13"))
        value["sdk-core-metadata-result"] = job("success", **locator("114", sdk="14"))
        forward_android(value)
        self.assertEqual(locator("114", sdk="14"), state.select_sdk_completion_state(value))
        for status in ("failure", "cancelled", "skipped", "in_progress"):
            changed = deepcopy(value)
            changed["sdk-core-metadata-result"]["result"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)
        for invalid in (locator("114", sdk="13"), locator("114", sdk="15")):
            changed = deepcopy(value)
            changed["sdk-core-metadata-result"]["outputs"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)

    def test_android_waves_fifteen_through_eighteen_are_terminal_and_ordered(self):
        value = handoff()
        value["sdk-core-metadata-result"] = job("success", **locator("114", sdk="14"))
        names = ("sdk-android-binary-result", "sdk-android-package-result",
                 "sdk-android-validation-result", "sdk-android-metadata-result")
        for wave, name in enumerate(names, start=15):
            value[name] = job("success", **locator(str(100 + wave), sdk=str(wave)))
        self.assertEqual(locator("118", sdk="18"), state.select_sdk_completion_state(value))
        for name in names:
            for result in ("failure", "cancelled", "skipped", "in_progress"):
                changed = deepcopy(value)
                changed[name]["result"] = result
                with self.subTest(name=name, result=result), self.assertRaises(ValueError):
                    state.select_sdk_completion_state(changed)
            changed = deepcopy(value)
            changed[name]["outputs"] = locator("199", sdk="14")
            with self.subTest(name=name, wrong_wave=True), self.assertRaises(ValueError):
                state.select_sdk_completion_state(changed)
        unchanged = handoff()
        unchanged["sdk-core-metadata-result"] = job("success", **locator("114", sdk="14"))
        for name in names:
            unchanged[name] = job("success", **locator("114", sdk="14"))
        self.assertEqual(locator("114", sdk="14"), state.select_sdk_completion_state(unchanged))

    def test_full_reuse_initial_and_normal_empty_sdk_branch_preserve_original_resume(self):
        value = needs()
        value["product-resume"]["outputs"]["full_reuse"] = "true"
        self.assertEqual(locator(), state.select_sdk_completion_state(value))
        for name in state._JOBS[1:]:
            value[name] = job()
        self.assertEqual(locator(), state.select_sdk_completion_state(value))
        value["product-resume"]["outputs"]["full_reuse"] = "false"
        with self.assertRaisesRegex(ValueError, "explicit original full reuse"):
            state.select_sdk_completion_state(value)

    def test_binary_only_collection_wins_over_its_runtime_parent(self):
        value = needs()
        value["runtime-continuation"]["outputs"].update(locator("74", "4"), aggregate_state="ready", aggregate_required="true")
        value["runtime-aggregate-continuation"] = job("success", **locator("75", "5"), aggregate_payload_complete="true")
        value["sdk-ios-binary-plan"] = job("success", sdk_workers_required="true")
        value["sdk-ios-binary"] = job("success")
        value["sdk-collect-3"] = job("success", artifact_id="83", artifact_digest="sha256:" + "b" * 64, wave_failed="false")
        self.assertEqual({**locator("83", sdk="3"), "artifact_digest": "sha256:" + "b" * 64}, state.select_sdk_completion_state(value))
        for name in ("sdk-ios-binary", "sdk-collect-3"):
            bad = deepcopy(value)
            bad[name] = job()
            with self.subTest(skipped=name), self.assertRaises(ValueError):
                state.select_sdk_completion_state(bad)
        value["sdk-collect-3"]["outputs"]["wave_failed"] = "true"
        with self.assertRaises(ValueError): state.select_sdk_completion_state(value)

    def test_runtime_latest_state_when_sdk_branch_absent(self):
        for wave in ("0", "1", "2", "3", "4"):
            value = needs()
            selected = locator("71" if wave == "0" else "74", wave)
            value["runtime-continuation"]["outputs"].update(selected)
            with self.subTest(wave=wave):
                self.assertEqual(selected, state.select_sdk_completion_state(value))
                value["runtime-continuation"]["outputs"].update(aggregate_state="completed", aggregate_required="false")
                value["runtime-aggregate-continuation"] = job("success", **selected, aggregate_payload_complete="true")
                self.assertEqual(selected, state.select_sdk_completion_state(value))
        value["runtime-continuation"]["outputs"].update(aggregate_state="ready", aggregate_required="true")
        value["runtime-aggregate-continuation"] = job("success", **locator("75", "5"), aggregate_payload_complete="true")
        self.assertEqual(locator("75", "5"), state.select_sdk_completion_state(value))

    def test_any_failed_cancelled_missing_or_nonterminal_branch_rejects_before_fallback(self):
        for baseline in (needs(), handoff()):
            for name in state._JOBS:
                for status in ("failure", "cancelled", "in_progress", "queued", None):
                    value = deepcopy(baseline)
                    value[name]["result"] = status
                    with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                        state.select_sdk_completion_state(value)
                value = deepcopy(baseline)
                del value[name]
                with self.subTest(missing=name), self.assertRaises(ValueError):
                    state.select_sdk_completion_state(value)

    def test_contradictory_elections_and_missing_success_locators_fail_closed(self):
        mutations = (
            ("product-resume", "full_reuse", "unknown"), ("product-resume", "wave_failed", "true"),
            ("runtime-continuation", "sdk_handoff_required", None), ("runtime-continuation", "aggregate_state", "unknown"),
            ("runtime-continuation", "aggregate_required", "true"),
            ("runtime-continuation", "state_wave", "5"), ("runtime-continuation", "artifact_id", "72"),
            ("sdk-ios-binary-plan", "sdk_workers_required", True), ("sdk-native-result", "artifact_id", "88"),
            ("sdk-ios-validation-result", "artifact_id", "99"),
            ("sdk-ios-metadata-result", "artifact_id", "110"),
        )
        for name, field, content in mutations:
            value = needs()
            value[name]["outputs"][field] = content
            with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                state.select_sdk_completion_state(value)
        for name in ("product-resume", "runtime-continuation", "sdk-plan", "sdk-native-result", "sdk-ios-validation-result",
                     "sdk-ios-metadata-result"):
            value = handoff()
            value[name]["outputs"].pop("artifact_id")
            with self.subTest(missing_locator=name), self.assertRaises(ValueError):
                state.select_sdk_completion_state(value)
        for field, content in (("artifact_id", True), ("artifact_digest", "bad"),
                               ("state_wave", "4"), ("sdk_state_wave", "9")):
            value = handoff()
            value["sdk-native-result"]["outputs"][field] = content
            with self.subTest(field=field), self.assertRaises(ValueError):
                state.select_sdk_completion_state(value)
        for field, content in (("artifact_id", True), ("artifact_digest", "bad"),
                               ("state_wave", "4"), ("sdk_state_wave", "10")):
            value = handoff()
            value["sdk-ios-validation-result"]["outputs"][field] = content
            with self.subTest(final_field=field), self.assertRaises(ValueError):
                state.select_sdk_completion_state(value)

    def test_skipped_or_unelected_branches_cannot_hide_stale_state(self):
        value = needs()
        value["runtime-aggregate-continuation"] = job("success", **locator("75", "5"), aggregate_payload_complete="true")
        with self.assertRaises(ValueError): state.select_sdk_completion_state(value)
        for name in ("runtime-aggregate-continuation", "sdk-ios-binary", "sdk-collect-3", "sdk-plan"):
            value = needs()
            value[name]["outputs"].update(locator("99", sdk="3"))
            with self.subTest(name=name), self.assertRaises(ValueError):
                state.select_sdk_completion_state(value)
        value = handoff()
        value["sdk-plan"] = job()
        with self.assertRaises(ValueError): state.select_sdk_completion_state(value)


if __name__ == "__main__":
    unittest.main()
