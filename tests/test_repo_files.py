"""The seed's data files stay well-formed until app code replaces them."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_fleet_card_declares_required_keys() -> None:
    card = tomllib.loads((ROOT / ".fleet.toml").read_text(encoding="utf-8"))
    assert card["layer"] == "enabling"
    assert card["icon"]
    assert card["description"]


def test_sample_config_matches_the_agreed_settings() -> None:
    cfg = json.loads((ROOT / "config.sample.json").read_text(encoding="utf-8"))
    assert cfg["hotkey"]["toggle_draw"]
    assert cfg["screens"]["cover_all"] is True
    assert isinstance(cfg["fade"]["enabled"], bool)
    assert cfg["fade"]["delay_seconds"] > 0
    presets = cfg["presets"]
    assert len(presets) == 7, "keys 1 to 7 each map to one preset"
    for preset in presets:
        assert preset["thickness_px"] > 0
        assert 0 <= preset["transparency"]["percent"] <= 100
        assert preset["outline"]["thickness_px"] >= 0


def test_runtime_config_is_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "config.json" in ignored
    assert ".venv/" in ignored
