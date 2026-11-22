"""Settings: drawing (hotkey, fading, keep-awake, presets) and recording, one tab each."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from overmark import icons, theme, win32
from overmark.config import MAX_TRANSPARENCY_PERCENT, Settings
from overmark.keepawake import (
    MAX_DISTANCE_PX,
    MIN_INTERVAL_S,
    MODE_EXECUTION_STATE,
    MODE_NUDGE,
    QUICK_INTERVALS,
    KeepAwake,
    parse_interval,
)
from overmark.keymap import hotkey_clashes, normalize_combo, parse_hotkey
from overmark.recording.naming import TOKENS, validate_pattern
from overmark.recording.options import (
    FRAME_RATES,
    MAX_BITRATE_KBPS,
    SCREEN_ACTIVE,
    SCREEN_ALL,
    Microphone,
    RecordingOptions,
)

log = logging.getLogger(__name__)

PAUSE_NOTE = (
    "Pause ends the current part of the video and resume starts the next; about a second "
    "around each pause is not recorded. The parts are joined into one file on stop."
)
CONTAINER_CHOICES = (("MP4 (H.264)", "mp4"), ("MKV (H.264)", "mkv"), ("WebM (VP9)", "webm"))
QUALITY_CHOICES = (("Low (small files)", "low"), ("Medium", "medium"), ("High", "high"))
BACKEND_CHOICES = (
    ("Automatic", "auto"),
    ("GPU duplication (ddagrab)", "ddagrab"),
    ("GDI (gdigrab, slower)", "gdigrab"),
)
CAPTURE_NOTE = (
    "Ink shows in OBS Display Capture (a whole monitor). Window Capture of another "
    "application does not include it."
)


SCREEN_SHARE = 0.9  # the dialog never covers the whole screen; its tabs scroll instead
CHROME_PX = QSize(96, 170)  # tab bar, scroll bar, margins, error line and buttons
RECORDING_COLUMN_PX = 380  # room for a folder path and the longest combo label


def _scrolling(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(content)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.viewport().setAutoFillBackground(False)  # the dialog's themed canvas shows through
    content.setAutoFillBackground(False)
    return area


def sequence_to_combo(sequence: QKeySequence) -> str | None:
    """Turn a captured key sequence into a combo string, or None if empty."""
    if sequence.isEmpty():
        return None
    text = sequence.toString(QKeySequence.SequenceFormat.PortableText).split(",")[0]
    return normalize_combo(text.replace("Meta", "Win"))


class SettingsDialog(QDialog):
    """Edits a copy of the settings; ``apply`` decides whether the copy is accepted."""

    def __init__(
        self,
        settings: Settings,
        apply: Callable[[Settings], str | None],
        *,
        list_microphones: Callable[[str], list[str]] = lambda _path: [],
        screen_labels: list[str] | None = None,
    ) -> None:
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Overmark settings")
        self._apply = apply
        self.draft = copy.deepcopy(settings)
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            theme.RADIUS_SETTINGS, theme.SPACE_MD, theme.RADIUS_SETTINGS, theme.SPACE_MD
        )
        outer.setSpacing(theme.GUTTER)
        self.tabs = tabs = QTabWidget()
        tabs.setIconSize(QSize(theme.ICON_TITLE, theme.ICON_TITLE))
        outer.addWidget(tabs)
        drawing_tab = QWidget()
        root = QVBoxLayout(drawing_tab)
        root.setContentsMargins(theme.SPACE_XS, theme.SPACE_XS, theme.SPACE_XS, theme.SPACE_XS)
        root.setSpacing(theme.GUTTER)
        tabs.addTab(_scrolling(drawing_tab), "Drawing")

        hotkey_box = QGroupBox("Draw hotkey")
        hotkey_form = QFormLayout(hotkey_box)
        self.hotkey_edit = QKeySequenceEdit(
            QKeySequence(settings.toggle_hotkey.replace("win", "meta"))
        )
        self.hotkey_edit.setMaximumSequenceLength(1)
        hotkey_form.addRow("Toggle drawing", self.hotkey_edit)
        root.addWidget(hotkey_box)

        fade_box = QGroupBox("Fading")
        fade_form = QFormLayout(fade_box)
        self.fade_enabled = QCheckBox("Fade ink after a delay")
        self.fade_enabled.setChecked(settings.fade.enabled)
        self.fade_delay = QDoubleSpinBox()
        self.fade_delay.setRange(0.5, 3600)
        self.fade_delay.setDecimals(1)
        self.fade_delay.setSuffix(" s")
        self.fade_delay.setValue(settings.fade.delay_seconds)
        self.fade_delay.setEnabled(settings.fade.enabled)
        self.fade_enabled.toggled.connect(self.fade_delay.setEnabled)
        fade_form.addRow(self.fade_enabled)
        fade_form.addRow("Delay", self.fade_delay)
        root.addWidget(fade_box)

        awake_box = QGroupBox("Keep display awake")
        awake_form = QFormLayout(awake_box)
        awake = settings.keep_awake
        self.awake_enabled = QCheckBox("Keep the screen on during long sessions")
        self.awake_enabled.setChecked(awake.enabled)
        self.awake_mode = QComboBox()
        self.awake_mode.addItem("Ask Windows to keep the display on", MODE_EXECUTION_STATE)
        self.awake_mode.addItem("Nudge the pointer", MODE_NUDGE)
        self.awake_mode.setCurrentIndex(max(self.awake_mode.findData(awake.mode), 0))
        self.awake_interval = QComboBox()
        self.awake_interval.setEditable(True)
        for seconds in QUICK_INTERVALS:
            self.awake_interval.addItem(str(seconds))
        self.awake_interval.setCurrentText(str(awake.interval_seconds))
        self.awake_distance = QSpinBox()
        self.awake_distance.setRange(1, MAX_DISTANCE_PX)
        self.awake_distance.setSuffix(" px")
        self.awake_distance.setValue(awake.distance_px)
        awake_form.addRow(self.awake_enabled)
        awake_form.addRow("Method", self.awake_mode)
        awake_form.addRow(f"Nudge after idle (s, {MIN_INTERVAL_S} or more)", self.awake_interval)
        awake_form.addRow("Nudge distance", self.awake_distance)
        for nudge_only in (self.awake_interval, self.awake_distance):
            nudge_only.setEnabled(awake.mode == MODE_NUDGE)
        self.awake_mode.currentIndexChanged.connect(self._sync_awake_fields)
        root.addWidget(awake_box)

        preset_box = QGroupBox("Presets")
        preset_form = QFormLayout(preset_box)
        self.preset_pick = QComboBox()
        preset_form.addRow("Preset", self.preset_pick)
        self.name_edit = QLineEdit()
        preset_form.addRow("Name", self.name_edit)
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        preset_form.addRow("Colour", self.color_button)
        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(1, 120)
        self.thickness.setSuffix(" px")
        preset_form.addRow("Thickness", self.thickness)
        trans_row = QHBoxLayout()
        self.trans_enabled = QCheckBox("Transparent")
        self.trans_percent = QSpinBox()
        self.trans_percent.setRange(0, MAX_TRANSPARENCY_PERCENT)
        self.trans_percent.setSuffix(" %")
        trans_row.addWidget(self.trans_enabled)
        trans_row.addWidget(self.trans_percent)
        preset_form.addRow("Transparency", trans_row)
        outline_row = QHBoxLayout()
        self.outline_enabled = QCheckBox("Outline")
        self.outline_px = QDoubleSpinBox()
        self.outline_px.setRange(0, 12)
        self.outline_px.setSingleStep(0.5)
        self.outline_px.setSuffix(" px")
        outline_row.addWidget(self.outline_enabled)
        outline_row.addWidget(self.outline_px)
        preset_form.addRow("Dark outline", outline_row)
        root.addWidget(preset_box)

        self.name_edit.textEdited.connect(self._store_preset)
        for spin in (self.thickness, self.trans_percent, self.outline_px):
            spin.valueChanged.connect(self._store_preset)
        for box in (self.trans_enabled, self.outline_enabled):
            box.toggled.connect(self._store_preset)
        self.trans_enabled.toggled.connect(self.trans_percent.setEnabled)
        self.outline_enabled.toggled.connect(self.outline_px.setEnabled)
        self._fill_preset_names()
        self.preset_pick.currentIndexChanged.connect(self._load_preset)
        self._load_preset(0)

        note = QLabel(CAPTURE_NOTE)
        note.setObjectName("note")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)

        recording_tab = self._recording_tab(settings, list_microphones, screen_labels or [])
        tabs.addTab(_scrolling(recording_tab), "Recording")

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        outer.addWidget(self.error)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        outer.addLayout(buttons)

        self._tab_glyphs = (theme.BRAND_GLYPH, "video")
        self.apply_theme()
        self.setMinimumWidth(440)
        self._tab_contents = (drawing_tab, recording_tab)
        self._sized = False

    def apply_theme(self) -> None:
        """Restyle for the current light or dark scheme; also called when the system flips."""
        t = theme.tokens()
        self.setStyleSheet(theme.stylesheet(t))
        for index, glyph in enumerate(self._tab_glyphs):
            self.tabs.setTabIcon(index, icons.icon(glyph, t, theme.ICON_TITLE))
        self.browse.setIcon(icons.icon("folder", t, theme.ICON_INLINE))

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        win32.exclude_from_capture(int(self.winId()))
        if not self._sized:
            self._sized = True
            self._fit_to_screen()

    def _fit_to_screen(self) -> None:
        """Open at the tabs' natural size, never larger than the screen; the tabs scroll.

        Runs on first show: size hints are only right once the stylesheet has polished
        every child widget.
        """
        content = QSize()
        for widget in self._tab_contents:
            content = content.expandedTo(widget.sizeHint())
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        self.resize(
            min(content.width() + CHROME_PX.width(), int(available.width() * SCREEN_SHARE)),
            min(content.height() + CHROME_PX.height(), int(available.height() * SCREEN_SHARE)),
        )

    # ----- recording -----------------------------------------------------------------

    def _recording_tab(
        self,
        settings: Settings,
        list_microphones: Callable[[str], list[str]],
        screen_labels: list[str],
    ) -> QWidget:
        rec = settings.recording
        tab = QWidget()
        columns = QHBoxLayout(tab)
        columns.setContentsMargins(4, 4, 4, 4)
        columns.setSpacing(12)
        column = QVBoxLayout()
        column.setSpacing(12)
        columns.addLayout(column, 1)
        column.addStrut(RECORDING_COLUMN_PX)

        keys_box = QGroupBox("Recording hotkeys")
        keys_form = QFormLayout(keys_box)
        self.record_edit = self._combo_edit(settings.record_hotkey)
        self.pause_edit = self._combo_edit(settings.pause_hotkey)
        keys_form.addRow("Start / stop", self.record_edit)
        keys_form.addRow("Pause / resume", self.pause_edit)
        column.addWidget(keys_box)

        capture_box = QGroupBox("What to record")
        capture_form = QFormLayout(capture_box)
        self.rec_screen = QComboBox()
        self.rec_screen.addItem("All screens in one video", SCREEN_ALL)
        self.rec_screen.addItem("Screen under the pointer", SCREEN_ACTIVE)
        for number, label in enumerate(screen_labels, start=1):
            self.rec_screen.addItem(label, number)
        if isinstance(rec.screen, int) and self.rec_screen.findData(rec.screen) < 0:
            self.rec_screen.addItem(f"Screen {rec.screen} (not connected)", rec.screen)
        self.rec_screen.setCurrentIndex(max(self.rec_screen.findData(rec.screen), 0))
        self.rec_cursor = QCheckBox("Show the pointer")
        self.rec_cursor.setChecked(rec.cursor)
        self.rec_ink = QCheckBox("Include the ink")
        self.rec_ink.setChecked(rec.include_ink)
        self.rec_fps = QComboBox()
        for fps in FRAME_RATES:
            self.rec_fps.addItem(f"{fps} fps", fps)
        self.rec_fps.setCurrentIndex(max(self.rec_fps.findData(rec.frame_rate), 0))
        self.rec_backend = self._choice_combo(BACKEND_CHOICES, rec.backend)
        capture_form.addRow("Screen", self.rec_screen)
        capture_form.addRow(self.rec_cursor)
        capture_form.addRow(self.rec_ink)
        capture_form.addRow("Frame rate", self.rec_fps)
        capture_form.addRow("Capture method", self.rec_backend)
        column.addWidget(capture_box)
        column.addStretch(1)

        column = QVBoxLayout()
        column.setSpacing(12)
        columns.addLayout(column, 1)
        column.addStrut(RECORDING_COLUMN_PX)
        file_box = QGroupBox("File")
        file_form = QFormLayout(file_box)
        folder_row = QHBoxLayout()
        self.rec_folder = QLineEdit(rec.folder)
        self.rec_folder.setPlaceholderText("Videos\\Overmark")
        self.browse = browse = QPushButton("Browse…")
        browse.setIconSize(QSize(theme.ICON_INLINE, theme.ICON_INLINE))
        browse.clicked.connect(self._pick_folder)
        folder_row.addWidget(self.rec_folder, 1)
        folder_row.addWidget(browse)
        self.rec_pattern = QLineEdit(rec.name_pattern)
        self.rec_pattern.setToolTip(
            "Tokens: " + ", ".join("{" + t + "}" for t in TOKENS) + ". Existing files are "
            "never overwritten: -2, -3 and so on are added."
        )
        self.rec_container = self._choice_combo(CONTAINER_CHOICES, rec.container)
        self.rec_quality = self._choice_combo(QUALITY_CHOICES, rec.quality)
        self.rec_bitrate = QSpinBox()
        self.rec_bitrate.setRange(0, MAX_BITRATE_KBPS)
        self.rec_bitrate.setSingleStep(500)
        self.rec_bitrate.setSuffix(" kbps")
        self.rec_bitrate.setSpecialValueText("Automatic (from quality)")
        self.rec_bitrate.setValue(rec.bitrate_kbps)
        file_form.addRow("Folder", folder_row)
        file_form.addRow("Name", self.rec_pattern)
        file_form.addRow("Format", self.rec_container)
        file_form.addRow("Quality", self.rec_quality)
        file_form.addRow("Bitrate (advanced)", self.rec_bitrate)
        column.addWidget(file_box)

        audio_box = QGroupBox("Audio and ffmpeg")
        audio_form = QFormLayout(audio_box)
        self.rec_mic = QCheckBox("Record the microphone")
        self.rec_mic.setChecked(rec.microphone.enabled)
        self.rec_mic_device = QComboBox()
        devices = list_microphones(rec.ffmpeg_path)
        if rec.microphone.device and rec.microphone.device not in devices:
            devices.insert(0, rec.microphone.device)
        self.rec_mic_device.addItems(devices)
        self.rec_mic_device.setCurrentText(rec.microphone.device)
        self.rec_mic_device.setEnabled(rec.microphone.enabled and bool(devices))
        self.rec_mic.toggled.connect(
            lambda on: self.rec_mic_device.setEnabled(on and self.rec_mic_device.count() > 0)
        )
        self.rec_ffmpeg = QLineEdit(rec.ffmpeg_path)
        self.rec_ffmpeg.setPlaceholderText("found on PATH")
        audio_form.addRow(self.rec_mic)
        audio_form.addRow("Microphone", self.rec_mic_device)
        audio_form.addRow("ffmpeg", self.rec_ffmpeg)
        column.addWidget(audio_box)

        note = QLabel(PAUSE_NOTE)
        note.setObjectName("note")
        note.setWordWrap(True)
        column.addWidget(note)
        column.addStretch(1)
        return tab

    @staticmethod
    def _combo_edit(combo: str) -> QKeySequenceEdit:
        edit = QKeySequenceEdit(QKeySequence(combo.replace("win", "meta")))
        edit.setMaximumSequenceLength(1)
        return edit

    @staticmethod
    def _choice_combo(choices: tuple[tuple[str, str], ...], current: str) -> QComboBox:
        box = QComboBox()
        for label, value in choices:
            box.addItem(label, value)
        box.setCurrentIndex(max(box.findData(current), 0))
        return box

    def _pick_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Recording folder", self.rec_folder.text())
        if chosen:
            self.rec_folder.setText(chosen)

    @staticmethod
    def _read_hotkey(edit: QKeySequenceEdit, what: str) -> str:
        combo = sequence_to_combo(edit.keySequence())
        if combo is None:
            raise ValueError(f"{what}: press a key combination")
        try:
            parse_hotkey(combo)
        except ValueError as exc:
            raise ValueError(f"{what}: {exc}") from None
        return combo

    def _read_recording(self) -> RecordingOptions:
        """The recording tab as options; raise ``ValueError`` with a message to show."""
        try:
            pattern = validate_pattern(self.rec_pattern.text())
        except ValueError as exc:
            raise ValueError(f"Recording: {exc}") from None
        device = self.rec_mic_device.currentText().strip()
        if self.rec_mic.isChecked() and not device:
            raise ValueError("Recording: pick a microphone, or switch the microphone off")
        return RecordingOptions(
            folder=self.rec_folder.text().strip(),
            name_pattern=pattern,
            container=str(self.rec_container.currentData()),
            quality=str(self.rec_quality.currentData()),
            bitrate_kbps=self.rec_bitrate.value(),
            frame_rate=int(self.rec_fps.currentData()),
            screen=self.rec_screen.currentData(),
            cursor=self.rec_cursor.isChecked(),
            include_ink=self.rec_ink.isChecked(),
            microphone=Microphone(enabled=self.rec_mic.isChecked(), device=device),
            backend=str(self.rec_backend.currentData()),
            ffmpeg_path=self.rec_ffmpeg.text().strip(),
        )

    def _sync_awake_fields(self) -> None:
        nudge = self.awake_mode.currentData() == MODE_NUDGE
        self.awake_interval.setEnabled(nudge)
        self.awake_distance.setEnabled(nudge)

    # ----- presets -------------------------------------------------------------

    def _fill_preset_names(self) -> None:
        current = max(self.preset_pick.currentIndex(), 0)
        self.preset_pick.blockSignals(True)
        self.preset_pick.clear()
        for i, preset in enumerate(self.draft.presets):
            self.preset_pick.addItem(f"{i + 1}  {preset.name}")
        self.preset_pick.setCurrentIndex(current)
        self.preset_pick.blockSignals(False)

    def _load_preset(self, index: int) -> None:
        preset = self.draft.presets[index]
        self._loading = True
        self.name_edit.setText(preset.name)
        self._show_color(preset.color)
        self.thickness.setValue(preset.thickness_px)
        self.trans_enabled.setChecked(preset.transparency.enabled)
        self.trans_percent.setValue(preset.transparency.percent)
        self.trans_percent.setEnabled(preset.transparency.enabled)
        self.outline_enabled.setChecked(preset.outline.enabled)
        self.outline_px.setValue(preset.outline.thickness_px)
        self.outline_px.setEnabled(preset.outline.enabled)
        self._loading = False

    def _store_preset(self, *_args) -> None:
        if self._loading:
            return
        preset = self.draft.presets[self.preset_pick.currentIndex()]
        preset.name = self.name_edit.text().strip() or preset.name
        preset.thickness_px = self.thickness.value()
        preset.transparency.enabled = self.trans_enabled.isChecked()
        preset.transparency.percent = self.trans_percent.value()
        preset.outline.enabled = self.outline_enabled.isChecked()
        preset.outline.thickness_px = self.outline_px.value()
        index = self.preset_pick.currentIndex()
        self.preset_pick.setItemText(index, f"{index + 1}  {preset.name}")

    def _show_color(self, color: str) -> None:
        self.color_button.setText(color)
        # Light text on dark ink and dark text on light ink, whatever the window theme.
        text = theme.LIGHT["fg"] if QColor(color).lightnessF() > 0.5 else theme.DARK["fg"]
        self.color_button.setStyleSheet(
            f"background: {color}; color: {text}; border-radius: {theme.RADIUS_MD}px;"
        )

    def _pick_color(self) -> None:
        preset = self.draft.presets[self.preset_pick.currentIndex()]
        chosen = QColorDialog.getColor(QColor(preset.color), self, "Ink colour")
        if chosen.isValid():
            preset.color = chosen.name().upper()
            self._show_color(preset.color)

    # ----- save --------------------------------------------------------------------

    def _save(self) -> None:
        try:
            combo = self._read_hotkey(self.hotkey_edit, "Draw hotkey")
            record_combo = self._read_hotkey(self.record_edit, "Start/stop recording hotkey")
            pause_combo = self._read_hotkey(self.pause_edit, "Pause recording hotkey")
            recording = self._read_recording()
        except ValueError as exc:
            self._show_error(f"{exc}.")
            return
        clashes = hotkey_clashes(
            {
                "Draw": combo,
                "Start/stop recording": record_combo,
                "Pause recording": pause_combo,
            },
            self.draft.keys,
        )
        if clashes:
            self._show_error("Hotkeys clash: " + "; ".join(clashes) + ".")
            return
        try:
            interval = parse_interval(self.awake_interval.currentText())
        except ValueError as exc:
            self._show_error(f"Keep-awake: {exc}. The previous value is kept.")
            return
        self.draft.toggle_hotkey = combo
        self.draft.record_hotkey = record_combo
        self.draft.pause_hotkey = pause_combo
        self.draft.recording = recording
        self.draft.fade.enabled = self.fade_enabled.isChecked()
        self.draft.fade.delay_seconds = self.fade_delay.value()
        self.draft.keep_awake = KeepAwake(
            enabled=self.awake_enabled.isChecked(),
            mode=str(self.awake_mode.currentData()),
            interval_seconds=interval,
            distance_px=self.awake_distance.value(),
        )
        problem = self._apply(copy.deepcopy(self.draft))
        if problem:
            self._show_error(problem)
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
