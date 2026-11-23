from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.auth import AuthError, AuthService
from sentriface.cli import _authorize_cli
from sentriface.storage.sqlite_store import SQLiteIdentityStore


PASSWORD = "correct horse battery staple"


class CliAuthorizationTest(unittest.TestCase):
    def test_first_run_only_allows_database_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth = self._service(Path(directory))
            _authorize_cli(auth, "init-db", None)
            with self.assertRaises(AuthError) as caught:
                _authorize_cli(auth, "profile", None)
            self.assertEqual(caught.exception.code, "setup_required")

    def test_cli_commands_enforce_role_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth = self._service(Path(directory))
            administrator, _ = auth.signup_initial("owner", "Owner", PASSWORD)
            auth.create_user(administrator, "reader", "Reader", "reader password long enough", ["viewer"])
            auth.create_user(administrator, "keeper", "Keeper", "keeper password long enough", ["custodian"])
            with auth._connect() as connection:
                connection.execute("UPDATE app_users SET must_change_password = 0")

            with patch("sentriface.cli.getpass.getpass", return_value="reader password long enough"):
                _authorize_cli(auth, "persons", "reader")
                with self.assertRaises(AuthError) as caught:
                    _authorize_cli(auth, "delete-person", "reader")
                self.assertEqual(caught.exception.code, "permission_denied")

            with patch("sentriface.cli.getpass.getpass", return_value="keeper password long enough"):
                _authorize_cli(auth, "delete-person", "keeper")
                with self.assertRaises(AuthError) as caught:
                    _authorize_cli(auth, "init-db", "keeper")
                self.assertEqual(caught.exception.code, "permission_denied")

            with patch("sentriface.cli.getpass.getpass", return_value=PASSWORD):
                _authorize_cli(auth, "init-db", "owner")

    def test_cli_refuses_an_administrator_set_password_until_it_is_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth = self._service(Path(directory))
            administrator, _ = auth.signup_initial("owner", "Owner", PASSWORD)
            auth.create_user(administrator, "keeper", "Keeper", "keeper password long enough", ["custodian"])
            with patch("sentriface.cli.getpass.getpass", return_value="keeper password long enough"):
                with self.assertRaises(AuthError) as caught:
                    _authorize_cli(auth, "persons", "keeper")
            self.assertEqual(caught.exception.code, "password_change_required")

    @staticmethod
    def _service(directory: Path) -> AuthService:
        database = directory / "sentriface.db"
        key = bytes(range(32))
        SQLiteIdentityStore(
            database,
            512,
            backup_dir=directory / "backups",
            database_key=key,
        ).initialize()
        return AuthService(database, key)


if __name__ == "__main__":
    unittest.main()