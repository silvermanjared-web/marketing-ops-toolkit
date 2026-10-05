from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.execution.bounded import invoke


class ExecutionSecurityTests(unittest.TestCase):
    def test_write_refuses_without_confirmation(self):
        with TemporaryDirectory() as tmp:
            result = invoke(
                "mutation.audit_snapshot",
                output_root=Path(tmp),
                relative_path="audit.json",
                content="{}",
            )
            self.assertEqual(result["status"], "refused")
            self.assertFalse((Path(tmp) / "audit.json").exists())

    def test_parent_path_is_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                invoke(
                    "mutation.recommendations_export",
                    confirm=True,
                    output_root=Path(tmp) / "safe",
                    relative_path="../other.md",
                    content="blocked",
                )

    def test_unknown_mutation_refuses(self):
        result = invoke("mutation.unknown", confirm=True)
        self.assertEqual(result["status"], "refused")


if __name__ == "__main__":
    unittest.main()
