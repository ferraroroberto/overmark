"""The Recording tab's system-audio controls, driven offscreen."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from overmark.config import Settings  # noqa: E402
from overmark.settings_dialog import SettingsDialog  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def dialog(outputs: list[str], saved: list[Settings], errors: list[str]) -> SettingsDialog:
    def apply(settings: Settings) -> None:
        saved.append(settings)

    box = SettingsDialog(Settings(), apply, list_system_audio=lambda: list(outputs))
    box._show_error = errors.append
    return box


def test_system_audio_on_with_no_device_shows_an_error_and_saves_nothing(app) -> None:
    saved, errors = [], []
    box = dialog([], saved, errors)
    box.rec_sys.setChecked(True)
    box._save()
    assert saved == []
    assert errors and "system-audio device" in errors[0]


def test_picking_an_output_saves_it_and_the_default_saves_empty(app) -> None:
    saved, errors = [], []
    box = dialog(["Desk Speakers", "Room Display"], saved, errors)
    assert box.rec_sys_device.itemText(0) == "Default output"
    box.rec_sys.setChecked(True)
    box._save()
    box.rec_sys_device.setCurrentIndex(box.rec_sys_device.findData("Room Display"))
    box._save()
    assert errors == []
    assert [s.recording.system_audio.device for s in saved] == ["", "Room Display"]
    assert all(s.recording.system_audio.enabled for s in saved)
