"""Failed SDK collection selection cannot bypass an earlier or later failure."""

from copy import deepcopy
import unittest

from ci.sdk_partial_state import _WAVES, select_failed_sdk_wave_state


def jobs(failed_wave):
    result = {f"sdk-collect-{wave}": {"result": "skipped", "outputs": {}} for wave in _WAVES}
    chosen = _WAVES.index(failed_wave)
    for index, wave in enumerate(_WAVES[:chosen + 1]):
        result[f"sdk-collect-{wave}"] = {"result": "success", "outputs": {
            "wave_failed": "true" if index == chosen else "false",
            "artifact_id": str(100 + wave), "artifact_digest": "sha256:" + "a" * 64}}
    return result


class SdkPartialStateTest(unittest.TestCase):
    def test_each_top_level_failed_collection_keeps_its_exact_upload(self):
        for wave in _WAVES:
            with self.subTest(wave=wave):
                original = jobs(wave)
                before = deepcopy(original)
                self.assertEqual({"artifact_id": str(100 + wave),
                                  "artifact_digest": "sha256:" + "a" * 64,
                                  "state_wave": "0", "sdk_state_wave": str(wave)},
                                 select_failed_sdk_wave_state(original))
                self.assertEqual(before, original)

    def test_rejects_incomplete_failed_or_forged_chain(self):
        for mutation in (
            lambda value: value["sdk-collect-3"].update(result="failure"),
            lambda value: value["sdk-collect-3"]["outputs"].update(wave_failed="true"),
            lambda value: value["sdk-collect-3"]["outputs"].update(artifact_id=""),
            lambda value: value["sdk-collect-3"]["outputs"].update(sdk_state_wave="9"),
            lambda value: value["sdk-collect-2"].update(result="success"),
            lambda value: value["sdk-collect-4"].update(result="success"),
            lambda value: value["sdk-collect-1"]["outputs"].update(artifact_id="0"),
            lambda value: value["sdk-collect-1"]["outputs"].update(artifact_digest="sha256:bad"),
            lambda value: value["sdk-collect-1"]["outputs"].update(sdk_state_wave="2"),
            lambda value: value["sdk-collect-1"]["outputs"].update(state_wave="5"),
            lambda value: value["sdk-collect-5"]["outputs"].update(artifact_id="999"),
        ):
            value = jobs(1)
            mutation(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_failed_sdk_wave_state(value)


if __name__ == "__main__":
    unittest.main()
