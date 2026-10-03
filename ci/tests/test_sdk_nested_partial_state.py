"""A failed nested SDK child cannot bypass predecessors or successors."""

from copy import deepcopy
import unittest

from ci.sdk_nested_partial_state import _CHILDREN, select_failed_nested_sdk_wave


def children(failed_wave):
    result = {name: {"result": "skipped", "outputs": {}} for name in _CHILDREN}
    for index, name in enumerate(_CHILDREN[:failed_wave - 10]):
        if index + 11 == failed_wave:
            result[name] = {"result": "failure", "outputs": {}}
        else:
            result[name] = {"result": "success", "outputs": {
                "artifact_id": str(100 + index),
                "artifact_digest": "sha256:" + "a" * 64,
                "state_wave": "0", "sdk_state_wave": str(index + 11)}}
    return result


class NestedSdkPartialStateTest(unittest.TestCase):
    def test_each_failed_child_selects_only_its_wave(self):
        for wave in range(11, 17):
            with self.subTest(wave=wave):
                original = children(wave)
                before = deepcopy(original)
                self.assertEqual({"wave": wave}, select_failed_nested_sdk_wave(original))
                self.assertEqual(before, original)

    def test_ambiguous_or_incomplete_chain_rejects(self):
        for mutation in (
            lambda value: value[_CHILDREN[0]].update(result="cancelled"),
            lambda value: value[_CHILDREN[0]].update(result="skipped"),
            lambda value: value[_CHILDREN[0]]["outputs"].update(artifact_id=""),
            lambda value: value[_CHILDREN[0]]["outputs"].update(artifact_digest="bad"),
            lambda value: value[_CHILDREN[0]]["outputs"].update(sdk_state_wave="16"),
            lambda value: value[_CHILDREN[0]]["outputs"].update(
                state_wave="5", sdk_state_wave="11"),
            lambda value: value[_CHILDREN[1]]["outputs"].update(sdk_state_wave="11"),
            lambda value: value[_CHILDREN[2]].update(result="success"),
            lambda value: value[_CHILDREN[2]].update(result="failure"),
            lambda value: value[_CHILDREN[2]]["outputs"].update(artifact_id="101"),
            lambda value: value[_CHILDREN[1]]["outputs"].update(
                artifact_id="101", artifact_digest="sha256:" + "a" * 64,
                state_wave="0", sdk_state_wave="12"),
        ):
            value = children(12)
            mutation(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_failed_nested_sdk_wave(value)

    def test_reused_predecessors_keep_an_inherited_locator(self):
        for inherited in (
            {"artifact_id": "77", "artifact_digest": "sha256:" + "a" * 64,
             "state_wave": "5", "sdk_state_wave": ""},
            {"artifact_id": "78", "artifact_digest": "sha256:" + "b" * 64,
             "state_wave": "0", "sdk_state_wave": "10"},
        ):
            value = children(13)
            value[_CHILDREN[0]]["outputs"] = inherited.copy()
            value[_CHILDREN[1]]["outputs"] = inherited.copy()
            with self.subTest(inherited=inherited):
                self.assertEqual({"wave": 13}, select_failed_nested_sdk_wave(value))

    def test_missing_failure_or_missing_job_rejects(self):
        no_failure = children(12)
        no_failure[_CHILDREN[1]] = {"result": "success", "outputs": {}}
        missing = children(12)
        del missing[_CHILDREN[0]]
        for value in (no_failure, missing):
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_failed_nested_sdk_wave(value)
