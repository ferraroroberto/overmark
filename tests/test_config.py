"""Config load, defaults, validation and round-trip."""

import json
from pathlib import Path

from overmark import config
from overmark.config import PRESET_COUNT, Settings, settings_from_dict, settings_to_dict
from overmark.keymap import DEFAULT_KEYS

ROOT = Path(__file__).resolve().parent.parent


def test_missing_config_is_created_from_the_sample(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    settings = config.load(target, ROOT / "config.sample.json")
    assert target.exists()
    assert settings.toggle_hotkey == "ctrl+alt+d"
    assert len(settings.presets) == PRESET_COUNT


def test_sample_matches_built_in_defaults() -> None:
    sample = json.loads((ROOT / "config.sample.json").read_text(encoding="utf-8"))
    assert settings_from_dict(sample) == Settings()


def test_defaults_are_compression_safe() -> None:
    s = Settings()
    assert s.sizes.highlighter_px == 28 and s.sizes.text_px == 32
    assert s.sizes.laser_dot_px == 18 and s.sizes.laser_halo_px == 6
    solid = s.presets[:6]
    assert all(p.thickness_px == 6 and p.outline.enabled for p in solid)
    colors = {p.color for p in s.presets}
    assert "#FF0000" not in colors and "#0000FF" not in colors


def test_round_trip_preserves_edits(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    s = Settings()
    s.toggle_hotkey = "ctrl+shift+f9"
    s.fade.enabled = False
    s.fade.delay_seconds = 3.5
    s.presets[2].color = "#ABCDEF"
    s.presets[2].transparency.enabled = True
    s.presets[2].transparency.percent = 40
    s.presets[2].outline.thickness_px = 1.5
    config.save(s, target)
    assert config.load(target, tmp_path / "no-sample.json") == s
    assert not target.with_name("config.json.tmp").exists()


def test_invalid_values_fall_back_per_key() -> None:
    raw = settings_to_dict(Settings())
    raw["hotkey"]["toggle_draw"] = "d"  # no modifier: not allowed globally
    raw["fade"]["delay_seconds"] = "soon"
    raw["presets"][0]["color"] = "yellow"
    raw["presets"][1]["thickness_px"] = 999
    raw["presets"][2]["transparency"]["percent"] = 100
    raw["keys"]["clear"] = "ctrl+"
    raw["keys"]["teleport"] = "q"
    s = settings_from_dict(raw)
    assert s.toggle_hotkey == "ctrl+alt+d"
    assert s.fade.delay_seconds == 8.0
    assert s.presets[0].color == "#FFE600"
    assert s.presets[1].thickness_px == 120
    assert s.presets[2].transparency.percent == config.MAX_TRANSPARENCY_PERCENT
    assert s.keys["clear"] == DEFAULT_KEYS["clear"]
    assert "teleport" not in s.keys


def test_short_preset_list_is_padded_with_defaults() -> None:
    raw = settings_to_dict(Settings())
    raw["presets"] = raw["presets"][:2]
    assert len(settings_from_dict(raw).presets) == PRESET_COUNT


def test_malformed_file_is_left_alone(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text("{not json", encoding="utf-8")
    assert config.load(target, ROOT / "config.sample.json") == Settings()
    assert target.read_text(encoding="utf-8") == "{not json"


def test_toolbar_positions_round_trip_and_drop_bad_entries(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    s = Settings()
    s.toolbar_positions = {"0,0,1920x1080": (40, 50)}
    config.save(s, target)
    assert config.load(target, tmp_path / "no-sample.json") == s
    bad = {"a": [1], "b": [1, "2"], "c": None, "d": [3, 4]}
    assert settings_from_dict({"toolbar": {"positions": bad}}).toolbar_positions == {"d": (3, 4)}
