"""Signing-secret process isolation guard; no tooling is executed here."""

import os
import unittest
from unittest import mock

from ci.products.signing_isolation import SIGNING_SECRET, require_no_signing_secret


class SigningIsolationTest(unittest.TestCase):
    def test_absent_secret_is_accepted_without_mutating_environments(self):
        supplied = {"PATH": "/synthetic/bin"}
        with mock.patch.dict(os.environ, {"PATH": "/current/bin"}, clear=True):
            current = dict(os.environ)
            self.assertIsNone(require_no_signing_secret(supplied))
            self.assertEqual({"PATH": "/synthetic/bin"}, supplied)
            self.assertEqual(current, dict(os.environ))

    def test_supplied_secret_presence_is_rejected_even_when_empty(self):
        for value in ("", "private material"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {}, clear=True):
                supplied = {SIGNING_SECRET: value}
                before = dict(supplied)
                with self.assertRaisesRegex(ValueError, "outside the product signing-secret context"):
                    require_no_signing_secret(supplied)
                self.assertEqual(before, supplied)
                self.assertNotIn(SIGNING_SECRET, os.environ)

    def test_live_secret_presence_is_rejected_even_when_supplied_mapping_omits_it(self):
        for value in ("", "private material"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {SIGNING_SECRET: value}, clear=True):
                supplied = {"PATH": "/synthetic/bin"}
                current = dict(os.environ)
                with self.assertRaisesRegex(ValueError, "outside the product signing-secret context"):
                    require_no_signing_secret(supplied)
                self.assertEqual({"PATH": "/synthetic/bin"}, supplied)
                self.assertEqual(current, dict(os.environ))


if __name__ == "__main__":
    unittest.main()
