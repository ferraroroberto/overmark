"""Settings: draw hotkey, fading, keep-awake, and the seven presets."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from overmark import theme, win32
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
from overmark.keymap import normalize_combo, parse_hotkey

log = logging.getLogger(__name__)

CAPTURE_NOTE = (
    "Ink shows in OBS Display Capture (a whole monitor). Window Capture of another "
    "application does not include it."
)


def sequence_to_combo(sequence: QKeySequence) -> str | None:
    """Turn a captured key sequence into a combo string, or None if empty."""
    if sequence.isEmpty():
        return None
    text = sequence.toString(QKeySequence.SequenceFormat.PortableText).split(",")[0]
    return normalize_combo(text.replace("Meta", "Win"))


class SettingsDialog(QDialog):
    """Edits a copy of the settings; ``apply`` decides whether the copy is accepted."""

    def __init__(self, settings: Settings, apply: Callable[[Settings], str | None]) -> None:
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Overmark settings")
        self._apply = apply
        self.draft = copy.deepcopy(settings)
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

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

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)

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
        root.addLayout(buttons)

        self.setStyleSheet(theme.stylesheet(theme.tokens()))
        self.setMinimumWidth(440)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        win32.exclude_from_capture(int(self.winId()))

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
        text = "#111111" if QColor(color).lightnessF() > 0.5 else "#ffffff"
        self.color_button.setStyleSheet(f"background: {color}; color: {text}; border-radius: 12px;")

    def _pick_color(self) -> None:
        preset = self.draft.presets[self.preset_pick.currentIndex()]
        chosen = QColorDialog.getColor(QColor(preset.color), self, "Ink colour")
        if chosen.isValid():
            preset.color = chosen.name().upper()
            self._show_color(preset.color)

    # ----- save --------------------------------------------------------------------

    def _save(self) -> None:
        try:
            combo = sequence_to_combo(self.hotkey_edit.keySequence())
            if combo is None:
                raise ValueError("press a key combination for the draw hotkey")
            parse_hotkey(combo)
        except ValueError as exc:
            self._show_error(f"Draw hotkey: {exc}.")
            return
        try:
            interval = parse_interval(self.awake_interval.currentText())
        except ValueError as exc:
            self._show_error(f"Keep-awake: {exc}. The previous value is kept.")
            return
        self.draft.toggle_hotkey = combo
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
