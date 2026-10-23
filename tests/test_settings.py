import json
import os

import pytest

from screen_translate import settings


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is only available on Windows")
def test_saved_cloud_key_is_encrypted_and_round_trips(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "config_path", lambda: path)
    preferences = settings.Settings(api_key="test-private-cloud-key", provider="official")
    preferences.save()
    content = path.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert "test-private-cloud-key" not in content
    assert "api_key" not in payload
    assert payload["encrypted_api_key"]
    assert settings.Settings.load().api_key == "test-private-cloud-key"
    assert not path.with_suffix(".tmp").exists()


def test_environment_key_is_used_only_when_no_local_key_exists(monkeypatch):
    monkeypatch.setenv("GOOGLE_TRANSLATE_API_KEY", "environment-test-key")
    assert settings.Settings().effective_api_key == "environment-test-key"
    assert settings.Settings(api_key="local-test-key").effective_api_key == "local-test-key"


def test_invalid_encrypted_key_does_not_break_other_preferences(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"target_language": "en", "encrypted_api_key": "broken"}), encoding="utf-8")
    monkeypatch.setattr(settings, "config_path", lambda: path)
    loaded = settings.Settings.load()
    assert loaded.target_language == "en"
    assert loaded.api_key == ""
