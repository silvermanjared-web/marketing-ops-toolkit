from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.execution.bounded import discover, invoke


class ExecutionLayerTests(unittest.TestCase):
    def test_exactly_five_bounded_mutations(self):
        registry = discover()
        writes = [name for name, spec in registry.items() if spec["effect"] == "write"]
        self.assertEqual(len(writes), 5)
        self.assertTrue(all(registry[name]["requires_confirmation"] for name in writes))

    def test_local_artifact_write_returns_receipt(self):
        with TemporaryDirectory() as tmp:
            result = invoke(
                "mutation.brief_write",
                confirm=True,
                output_root=Path(tmp),
                relative_path="briefs/weekly.md",
                content="decision-ready",
            )
            self.assertEqual(result["status"], "executed")
            self.assertEqual(result["effect"], "write")
            self.assertEqual((Path(tmp) / "briefs/weekly.md").read_text(), "decision-ready")

    def test_preview_is_non_mutating_contract(self):
        result = invoke("gmail.preview_rules")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["effect"], "read")


if __name__ == "__main__":
    unittest.main()
