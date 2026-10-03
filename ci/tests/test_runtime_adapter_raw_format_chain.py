"""Original pretty producer bytes survive real receipt/attestation composition."""

from pathlib import Path
import tempfile
import unittest

from ci.products.inventory import load_json_bytes, regular_file_inventory
from ci.tests.test_product_native_chain import build_chain


class RuntimeAdapterRawFormatChainTest(unittest.TestCase):
    def test_pretty_original_reports_preserve_runtime_and_sdk_product_bytes(self):
        with tempfile.TemporaryDirectory(prefix="adapter-raw-format-") as temporary:
            root = Path(temporary).resolve()
            first = build_chain(root / "compact", 1)
            original_inventory = regular_file_inventory(first["root"], allow_empty=True)
            context = {**first["context"], "adapter_report_format": "pretty",
                       "producer": {**first["context"]["producer"], "commit": f"{2:040x}", "runId": 2}}
            second = build_chain(root / "pretty", 2, variants=first["variants"], context=context)
            self.assertEqual(original_inventory, regular_file_inventory(first["root"], allow_empty=True))
            self.assertEqual(first["aggregate"].read_bytes(), second["aggregate"].read_bytes())
            self.assertEqual(first["compatibility"].read_bytes(), second["compatibility"].read_bytes())
            for component, reports in second["adapters"]["adapter_report_files"].items():
                for target, report in reports.items():
                    raw = report.read_bytes()
                    self.assertIn(b'\n    "', raw)
                    previous = first["adapters"]["adapter_report_files"][component][target].read_bytes()
                    self.assertNotEqual(previous, raw)
                    self.assertEqual("passed", load_json_bytes(raw)["result"])


if __name__ == "__main__":
    unittest.main()
