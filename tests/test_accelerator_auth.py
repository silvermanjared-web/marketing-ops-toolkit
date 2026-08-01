from __future__ import annotations

import fnmatch
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

def stub_module(name: str, **attributes: object) -> None:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules.setdefault(name, module)


stub_module("google")
stub_module("google.auth")
stub_module("google.auth.transport")
stub_module("google.auth.transport.requests", Request=object)
stub_module("google.oauth2")
stub_module("google.oauth2.credentials", Credentials=type("Credentials", (), {}))
stub_module("google_auth_oauthlib")
stub_module(
    "google_auth_oauthlib.flow",
    InstalledAppFlow=type("InstalledAppFlow", (), {}),
)
stub_module("googleapiclient")
stub_module("googleapiclient.discovery", build=lambda *args, **kwargs: None)
stub_module("googleapiclient.errors", HttpError=type("HttpError", (Exception,), {}))

from src.inbox import accelerator


class AcceleratorAuthTests(unittest.TestCase):
    def test_legacy_file_is_used_when_default_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "token.json"
            legacy.write_text("legacy", encoding="utf-8")
            with mock.patch("pathlib.Path.cwd", return_value=root):
                resolved = accelerator.resolve_oauth_file(
                    None, root / "config" / "token.json", "token.json"
                )
            self.assertEqual(resolved, legacy)

    def test_explicit_file_does_not_fall_back(self) -> None:
        explicit = Path("custom/token.json")
        self.assertEqual(
            accelerator.resolve_oauth_file(
                explicit, accelerator.DEFAULT_TOKEN_FILE, "token.json"
            ),
            explicit,
        )

    def test_failed_replace_preserves_existing_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token.json"
            token.write_text("old-token", encoding="utf-8")
            temporary_names: list[str] = []

            def fail_replace(source: str | Path, destination: str | Path) -> None:
                temporary_names.append(Path(source).name)
                raise OSError("simulated failure")

            with mock.patch("os.replace", side_effect=fail_replace):
                with self.assertRaisesRegex(OSError, "simulated failure"):
                    accelerator.write_token_securely(token, "new-token")
            self.assertEqual(token.read_text(encoding="utf-8"), "old-token")
            self.assertEqual(list(token.parent.glob("token-*.json")), [])
            self.assertEqual(len(temporary_names), 1)
            temporary_name = temporary_names[0]
            self.assertTrue(temporary_name.startswith("token-token-"))
            self.assertTrue(temporary_name.endswith(".json"))
            ignore_patterns = {
                line.strip()
                for line in accelerator.DEFAULT_CONFIG_DIR.parent.joinpath(".gitignore").read_text().splitlines()
                if line.strip() and not line.startswith("#")
            }
            self.assertTrue(
                any(fnmatch.fnmatch(temporary_name, pattern) for pattern in ignore_patterns),
                f"temporary token {temporary_name!r} is not ignored by Git",
            )

    @unittest.skipIf(os.name == "nt", "POSIX mode assertion")
    def test_atomic_write_creates_mode_0600_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token.json"
            accelerator.write_token_securely(token, "new-token")
            self.assertEqual(token.read_text(encoding="utf-8"), "new-token")
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)

    @unittest.skipIf(os.name == "nt", "POSIX mode assertion")
    def test_valid_existing_token_permissions_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token.json"
            token.write_text("{}", encoding="utf-8")
            token.chmod(0o644)
            credentials = mock.Mock(valid=True)
            with (
                mock.patch.object(
                    accelerator.Credentials,
                    "from_authorized_user_file",
                    return_value=credentials,
                    create=True,
                ),
                mock.patch.object(accelerator, "build", return_value="service"),
            ):
                service = accelerator.get_gmail_service(token_file=token)
            self.assertEqual(service, "service")
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
