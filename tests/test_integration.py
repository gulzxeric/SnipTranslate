from pathlib import Path
from unittest.mock import Mock

import pytest

from screen_translate import integration


def fake_exe(tmp_path: Path) -> Path:
    executable = tmp_path / "Snipaste with spaces.exe"
    executable.touch()
    return executable


def test_bad_path_has_actionable_error(tmp_path):
    with pytest.raises(integration.IntegrationError, match="找不到"):
        integration.snip_with_snipaste(str(tmp_path / "missing.exe"))
    with pytest.raises(integration.IntegrationError, match="选择"):
        integration.start_snipaste("")


def test_clipboard_command_uses_argument_list(tmp_path, monkeypatch):
    executable = fake_exe(tmp_path)
    popen = Mock()
    monkeypatch.setattr(integration.subprocess, "Popen", popen)
    integration.snip_with_snipaste(str(executable))
    args, kwargs = popen.call_args
    assert args == ([str(executable), "snip", "-o", "clipboard"],)
    assert kwargs["cwd"] == str(tmp_path)
    assert "shell" not in kwargs


@pytest.mark.parametrize("already_running", [False, True])
def test_starts_only_when_not_running(tmp_path, monkeypatch, already_running):
    executable = fake_exe(tmp_path)
    monkeypatch.setattr(integration, "is_snipaste_running", lambda _path: already_running)
    launch = Mock()
    monkeypatch.setattr(integration, "_launch", launch)
    assert integration.start_snipaste(str(executable)) is (not already_running)
    assert launch.call_count == (0 if already_running else 1)


def test_launch_failure_is_user_facing(tmp_path, monkeypatch):
    executable = fake_exe(tmp_path)
    monkeypatch.setattr(integration.subprocess, "Popen", Mock(side_effect=OSError("failure")))
    with pytest.raises(integration.IntegrationError, match="无法启动"):
        integration.snip_with_snipaste(str(executable))


def test_process_comparison_requires_same_installation(tmp_path, monkeypatch):
    executable = fake_exe(tmp_path)
    def images():
        yield str(tmp_path / "other" / executable.name)
        yield str(executable)
    monkeypatch.setattr(integration, "_process_images", images)
    assert integration.is_snipaste_running(str(executable))
