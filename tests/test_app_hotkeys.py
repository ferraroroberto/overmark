"""The tray's global hotkeys, offscreen, with Windows' registration faked."""

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from overmark import win32  # noqa: E402
from overmark.app import DRAW_HOTKEY_ID, PRESET_HOTKEY_IDS, OvermarkApp  # noqa: E402
from overmark.config import Settings  # noqa: E402
from overmark.keymap import parse_hotkey  # noqa: E402


class Windows:
    """Stands in for RegisterHotKey: refuses the ``taken`` combos, remembers the rest."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.taken: set[tuple[int, int]] = set()
        self.registered: dict[int, int] = {}  # id to virtual key
        self.pressed = 0
        monkeypatch.setattr(win32, "register_hotkey", self.register)
        monkeypatch.setattr(win32, "unregister_hotkey", lambda i: self.registered.pop(i, None))
        monkeypatch.setattr(win32, "hotkey_id_from_msg", lambda _message: self.pressed)

    def take(self, combo: str) -> None:
        self.taken.add(parse_hotkey(combo))

    def register(self, hotkey_id: int, modifiers: int, vk: int) -> bool:
        if (modifiers, vk) in self.taken:
            return False
        self.registered[hotkey_id] = vk
        return True


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> Windows:
    return Windows(monkeypatch)


@pytest.fixture
def make_app(qapp, windows: Windows, tmp_path):
    made: list[OvermarkApp] = []

    def make(**preset_hotkeys: str) -> OvermarkApp:
        settings = Settings()
        for name, combo in preset_hotkeys.items():
            settings.preset_hotkeys[int(name.removeprefix("preset_")) - 1] = combo
        app = OvermarkApp(qapp, settings, tmp_path / "config.json")
        app.notices = []
        app.tray.showMessage = lambda _title, text: app.notices.append(text)
        made.append(app)
        app.register_startup_hotkeys()
        return app

    yield make
    for app in made:
        qapp.removeNativeEventFilter(app.hotkey_filter)


def edited(app: OvermarkApp, **changes) -> Settings:
    settings = copy.deepcopy(app.controller.settings)
    for name, value in changes.items():
        setattr(settings, name, value)
    return settings


def presets(**combos: str) -> list[str]:
    return [combos.get(f"preset_{n}", "") for n in range(1, 8)]


def press(app: OvermarkApp, windows: Windows, hotkey_id: int) -> None:
    windows.pressed = hotkey_id
    app.hotkey_filter.nativeEventFilter(b"windows_generic_MSG", 0)


def test_no_preset_hotkey_is_registered_by_default(make_app, windows: Windows) -> None:
    make_app()
    assert not set(windows.registered) & set(PRESET_HOTKEY_IDS)
    assert DRAW_HOTKEY_ID in windows.registered


def test_a_preset_hotkey_picks_the_preset_and_starts_drawing(make_app, windows: Windows) -> None:
    app = make_app(preset_3="ctrl+alt+3", preset_7="ctrl+alt+7")

    press(app, windows, PRESET_HOTKEY_IDS[2])
    assert app.controller.drawing
    assert app.controller.cycler.index == 2

    press(app, windows, PRESET_HOTKEY_IDS[6])  # already drawing: only the preset changes
    assert app.controller.drawing
    assert app.controller.cycler.index == 6


def test_every_hotkey_refused_at_startup_is_named_in_one_notice(make_app, windows) -> None:
    windows.take("ctrl+alt+1")
    windows.take("ctrl+alt+2")
    app = make_app(preset_1="ctrl+alt+1", preset_2="ctrl+alt+2")
    assert app.notices == [
        "Hotkey not registered: Preset 1 (CTRL+ALT+1), Preset 2 (CTRL+ALT+2). "
        "Pick another in Settings."
    ]


def test_a_refused_combo_changes_nothing(make_app, windows: Windows) -> None:
    app = make_app(preset_1="ctrl+alt+1")
    before = dict(windows.registered)
    windows.take("ctrl+alt+9")

    problem = app.apply_settings(edited(app, preset_hotkeys=presets(preset_1="ctrl+alt+9")))

    assert problem == "CTRL+ALT+9 is already used by another application."
    assert windows.registered == before
    assert app.controller.settings.preset_hotkeys == presets(preset_1="ctrl+alt+1")


def test_hotkeys_refused_earlier_do_not_block_a_save(make_app, windows: Windows) -> None:
    windows.take("ctrl+alt+1")
    windows.take("ctrl+alt+2")
    app = make_app(preset_1="ctrl+alt+1", preset_2="ctrl+alt+2")

    # Move one off its taken combo while the other is still refused, then clear that one.
    first = presets(preset_1="ctrl+alt+5", preset_2="ctrl+alt+2")
    assert app.apply_settings(edited(app, preset_hotkeys=first)) is None
    assert PRESET_HOTKEY_IDS[0] in windows.registered
    assert app.apply_settings(edited(app, preset_hotkeys=presets(preset_1="ctrl+alt+5"))) is None
    assert PRESET_HOTKEY_IDS[1] not in windows.registered


def test_clearing_and_swapping_preset_hotkeys(make_app, windows: Windows) -> None:
    app = make_app(preset_1="ctrl+alt+1", preset_2="ctrl+alt+2")

    swapped = presets(preset_1="ctrl+alt+2", preset_2="ctrl+alt+1")
    assert app.apply_settings(edited(app, preset_hotkeys=swapped)) is None
    assert windows.registered[PRESET_HOTKEY_IDS[0]] == ord("2")
    assert windows.registered[PRESET_HOTKEY_IDS[1]] == ord("1")

    assert app.apply_settings(edited(app, preset_hotkeys=presets())) is None
    assert not set(windows.registered) & set(PRESET_HOTKEY_IDS)
