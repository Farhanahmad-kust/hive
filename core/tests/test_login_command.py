"""Tests for the ``hive login`` CLI command."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.runner.cli import (
    _save_aden_api_key_to_shell_config,
    _verify_aden_api_key,
    cmd_login,
)

# ---------------------------------------------------------------------------
# _verify_aden_api_key
# ---------------------------------------------------------------------------


class TestVerifyAdenApiKey:
    """Unit tests for the _verify_aden_api_key helper."""

    def test_returns_true_for_200(self):
        """A 200 response means the key is valid."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = _verify_aden_api_key("valid-key")

        assert result is True

    def test_returns_false_for_401(self):
        """A 401 response means the key is invalid."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = _verify_aden_api_key("bad-key")

        assert result is False

    def test_returns_false_for_403(self):
        """A 403 response is also treated as an invalid key."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = _verify_aden_api_key("forbidden-key")

        assert result is False

    def test_returns_none_on_network_error(self):
        """A network error should return None (inconclusive)."""
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("connection refused")
            mock_client_cls.return_value = mock_client

            result = _verify_aden_api_key("any-key")

        assert result is None

    def test_returns_none_when_httpx_unavailable(self):
        """If httpx is not installed, verification returns None."""
        with patch.dict(sys.modules, {"httpx": None}):
            result = _verify_aden_api_key("any-key")

        assert result is None


# ---------------------------------------------------------------------------
# _save_aden_api_key_to_shell_config
# ---------------------------------------------------------------------------


class TestSaveAdenApiKeyToShellConfig:
    """Unit tests for _save_aden_api_key_to_shell_config."""

    def test_writes_to_bashrc_by_default(self, tmp_path, monkeypatch):
        """When SHELL is not zsh, the key is written to ~/.bashrc."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        # Ensure aden_tools is not importable so we hit the fallback path
        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            result = _save_aden_api_key_to_shell_config("test-api-key")

        assert result is not None
        config_file = fake_home / ".bashrc"
        assert config_file.exists()
        content = config_file.read_text()
        assert "ADEN_API_KEY" in content
        assert "test-api-key" in content

    def test_writes_to_zshrc_for_zsh(self, tmp_path, monkeypatch):
        """When SHELL contains 'zsh', the key is written to ~/.zshrc."""
        monkeypatch.setenv("SHELL", "/bin/zsh")
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            result = _save_aden_api_key_to_shell_config("zsh-api-key")

        assert result is not None
        config_file = fake_home / ".zshrc"
        assert config_file.exists()
        content = config_file.read_text()
        assert "zsh-api-key" in content

    def test_updates_existing_key(self, tmp_path, monkeypatch):
        """An existing ADEN_API_KEY line is replaced rather than duplicated."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        bashrc = fake_home / ".bashrc"
        bashrc.write_text('\nexport ADEN_API_KEY="old-key"\n')

        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            _save_aden_api_key_to_shell_config("new-key")

        content = bashrc.read_text()
        assert "new-key" in content
        assert content.count("ADEN_API_KEY") == 1  # No duplicate

    def test_updates_key_at_start_of_file(self, tmp_path, monkeypatch):
        """An ADEN_API_KEY at the very start of the file (no leading newline) is replaced."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        bashrc = fake_home / ".bashrc"
        bashrc.write_text('export ADEN_API_KEY="start-key"\n# other config\n')

        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            _save_aden_api_key_to_shell_config("replaced-key")

        content = bashrc.read_text()
        assert "replaced-key" in content
        assert content.count("ADEN_API_KEY") == 1  # No duplicate

    def test_returns_none_on_permission_error(self, tmp_path, monkeypatch):
        """If the config file cannot be written, None is returned."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            with patch("pathlib.Path.write_text", side_effect=OSError("permission denied")):
                with patch("pathlib.Path.exists", return_value=False):
                    result = _save_aden_api_key_to_shell_config("key")

        assert result is None


# ---------------------------------------------------------------------------
# cmd_login
# ---------------------------------------------------------------------------


def _make_login_args(**kwargs):
    """Build a minimal Namespace for cmd_login."""
    defaults = {"api_key": None, "no_verify": True}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdLogin:
    """Integration-style tests for cmd_login."""

    def test_login_with_api_key_flag(self, tmp_path, monkeypatch, capsys):
        """--api-key flag bypasses the interactive prompt."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        monkeypatch.delenv("ADEN_API_KEY", raising=False)
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        args = _make_login_args(api_key="flag-key", no_verify=True)

        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            ret = cmd_login(args)

        assert ret == 0
        assert os.environ.get("ADEN_API_KEY") == "flag-key"
        out = capsys.readouterr().out
        assert "Logged in successfully" in out

    def test_login_uses_existing_env_var(self, tmp_path, monkeypatch, capsys):
        """If ADEN_API_KEY is already set, it is reused without prompting."""
        monkeypatch.setenv("ADEN_API_KEY", "existing-key")
        monkeypatch.setenv("SHELL", "/bin/bash")
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        args = _make_login_args(no_verify=True)

        with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                       "aden_tools.credentials.shell_config": None}):
            ret = cmd_login(args)

        assert ret == 0
        out = capsys.readouterr().out
        assert "Logged in successfully" in out

    def test_login_aborts_when_no_key_given(self, monkeypatch, capsys):
        """If no key is provided and the prompt is cancelled, return non-zero."""
        monkeypatch.delenv("ADEN_API_KEY", raising=False)

        args = _make_login_args(no_verify=True)

        # Simulate the user pressing Ctrl-C at the getpass prompt
        with patch("getpass.getpass", side_effect=KeyboardInterrupt):
            ret = cmd_login(args)

        assert ret != 0

    def test_login_aborts_on_empty_input(self, monkeypatch, capsys):
        """If the user enters an empty string, login is aborted."""
        monkeypatch.delenv("ADEN_API_KEY", raising=False)

        args = _make_login_args(no_verify=True)

        with patch("getpass.getpass", return_value=""):
            ret = cmd_login(args)

        assert ret != 0

    def test_login_with_verification_success(self, tmp_path, monkeypatch, capsys):
        """When verification succeeds the command reports success."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        monkeypatch.delenv("ADEN_API_KEY", raising=False)
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        args = _make_login_args(api_key="good-key", no_verify=False)

        with patch("framework.runner.cli._verify_aden_api_key", return_value=True):
            with patch.dict(sys.modules, {"aden_tools": None, "aden_tools.credentials": None,
                                           "aden_tools.credentials.shell_config": None}):
                ret = cmd_login(args)

        assert ret == 0
        out = capsys.readouterr().out
        assert "verified" in out.lower()
        assert "Logged in successfully" in out

    def test_login_with_verification_failure_user_aborts(self, monkeypatch, capsys):
        """When verification fails and the user does not confirm, return non-zero."""
        monkeypatch.delenv("ADEN_API_KEY", raising=False)

        args = _make_login_args(api_key="bad-key", no_verify=False)

        with patch("framework.runner.cli._verify_aden_api_key", return_value=False):
            with patch("builtins.input", return_value="n"):
                ret = cmd_login(args)

        assert ret != 0

    def test_login_with_verification_failure_user_proceeds(self, tmp_path, monkeypatch, capsys):
        """When verification fails but the user confirms, login still succeeds."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        monkeypatch.delenv("ADEN_API_KEY", raising=False)
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        args = _make_login_args(api_key="maybe-key", no_verify=False)

        with patch("framework.runner.cli._verify_aden_api_key", return_value=False):
            with patch("builtins.input", return_value="y"):
                with patch.dict(sys.modules, {"aden_tools": None,
                                               "aden_tools.credentials": None,
                                               "aden_tools.credentials.shell_config": None}):
                    ret = cmd_login(args)

        assert ret == 0
        assert os.environ.get("ADEN_API_KEY") == "maybe-key"


# ---------------------------------------------------------------------------
# CLI subcommand registration (subprocess)
# ---------------------------------------------------------------------------


class TestLoginCommandRegistration:
    """Verify that `python -m framework login --help` is properly registered."""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).resolve().parent.parent.parent

    def test_login_help_exits_zero(self, project_root):
        """``python -m framework login --help`` must exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "framework", "login", "--help"],
            capture_output=True,
            text=True,
            cwd=str(project_root / "core"),
        )
        assert result.returncode == 0
        assert "api-key" in result.stdout.lower() or "aden" in result.stdout.lower()
