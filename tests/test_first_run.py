from unittest.mock import Mock

from screen_translate import companion
from screen_translate.settings import Settings


def test_existing_snipaste_path_does_not_interrupt_startup(tmp_path, monkeypatch):
    executable = tmp_path / 'Snipaste.exe'
    executable.touch()
    dialog = Mock(side_effect=AssertionError('Valid installations do not need setup'))
    monkeypatch.setattr(companion.QFileDialog, 'getOpenFileName', dialog)
    preferences = Settings(snipaste_path=str(executable))
    assert companion.prepare_preferences(preferences) is preferences


def test_portable_first_run_saves_selected_snipaste_path(tmp_path, monkeypatch):
    executable = tmp_path / 'Snipaste.exe'
    executable.touch()
    monkeypatch.setattr(companion.QFileDialog, 'getOpenFileName', lambda *_: (str(executable), ''))
    saved = []
    monkeypatch.setattr(Settings, 'save', lambda self: saved.append(self.snipaste_path))
    preferences = Settings(snipaste_path=str(tmp_path / 'missing.exe'))
    selected = companion.prepare_preferences(preferences)
    assert selected.snipaste_path == str(executable.resolve())
    assert saved == [selected.snipaste_path]
    assert preferences.snipaste_path != selected.snipaste_path


def test_cancelled_first_run_exits_without_crash_or_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(companion.QFileDialog, 'getOpenFileName', lambda *_: ('', ''))
    save = Mock()
    monkeypatch.setattr(Settings, 'save', save)
    assert companion.prepare_preferences(Settings(snipaste_path=str(tmp_path / 'missing.exe'))) is None
    save.assert_not_called()
