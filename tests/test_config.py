import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool import config  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point config and Kaggle credentials at a temp dir, never the real home."""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "settings.json")
    # Without this the pre-rename fallback would read the real user's file.
    monkeypatch.setattr(config, "LEGACY_CONFIG_PATH", tmp_path / "legacy" / "settings.json")
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path / "kaggle"))
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    return tmp_path


class TestSettings:
    def test_defaults_fill_in_output_dirs(self):
        s = config.Settings()
        assert s.audio_dir and s.srt_dir
        assert s.arabic_threshold == 0.5

    def test_round_trip(self, isolated):
        s = config.Settings(font_en="Futura", arabic_threshold=0.25)
        config.save(s)
        assert config.load().font_en == "Futura"
        assert config.load().arabic_threshold == 0.25

    def test_missing_file_yields_defaults(self, isolated):
        assert config.load().font_en == config.Settings().font_en

    def test_corrupt_file_yields_defaults_instead_of_raising(self, isolated):
        config.CONFIG_PATH.write_text("{not json", encoding="utf-8")
        assert config.load().font_en == config.Settings().font_en

    def test_non_dict_json_yields_defaults(self, isolated):
        config.CONFIG_PATH.write_text("[1,2,3]", encoding="utf-8")
        assert isinstance(config.load(), config.Settings)

    def test_unknown_keys_are_ignored(self, isolated):
        config.CONFIG_PATH.write_text(
            json.dumps({"font_en": "Futura", "removed_option": 1}), encoding="utf-8"
        )
        assert config.load().font_en == "Futura"

    def test_settings_from_the_old_app_name_are_still_read(self, isolated):
        # Upgrading to the Krevon Scribe name must not reset someone's setup.
        config.LEGACY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.LEGACY_CONFIG_PATH.write_text(
            json.dumps({"kaggle_username": "olduser", "font_en": "Futura"}),
            encoding="utf-8",
        )
        loaded = config.load()
        assert loaded.kaggle_username == "olduser"
        assert loaded.font_en == "Futura"

    def test_the_new_location_wins_over_the_old_one(self, isolated):
        config.LEGACY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.LEGACY_CONFIG_PATH.write_text(
            json.dumps({"kaggle_username": "olduser"}), encoding="utf-8"
        )
        config.save(config.Settings(kaggle_username="newuser"))
        assert config.load().kaggle_username == "newuser"

    def test_a_corrupt_new_file_still_falls_back_to_the_old_one(self, isolated):
        config.CONFIG_PATH.write_text("{not json", encoding="utf-8")
        config.LEGACY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.LEGACY_CONFIG_PATH.write_text(
            json.dumps({"kaggle_username": "olduser"}), encoding="utf-8"
        )
        assert config.load().kaggle_username == "olduser"

    def test_save_is_atomic_leaving_no_temp_file(self, isolated):
        config.save(config.Settings())
        assert not list(isolated.glob("*.tmp"))


class TestKaggleCredentials:
    def test_reports_unconfigured_when_empty(self, isolated):
        assert config.kaggle_status()["configured"] is False

    def test_kaggle_json_written_and_detected(self, isolated):
        config.write_kaggle_json("someone", "abc123")
        status = config.kaggle_status()
        assert status["configured"] and status["username"] == "someone"

    def test_access_token_written_and_detected(self, isolated):
        config.write_access_token("tok_123")
        status = config.kaggle_status()
        assert status["configured"] and status["has_token_file"]

    def test_blank_credentials_rejected(self, isolated):
        with pytest.raises(ValueError):
            config.write_kaggle_json("", "key")
        with pytest.raises(ValueError):
            config.write_access_token("   ")

    def test_env_token_alone_counts_as_configured(self, isolated, monkeypatch):
        monkeypatch.setenv("KAGGLE_API_TOKEN", "tok")
        assert config.kaggle_status()["configured"] is True

    def test_unreadable_kaggle_json_does_not_raise(self, isolated):
        d = config.kaggle_dir(); d.mkdir(parents=True, exist_ok=True)
        (d / "kaggle.json").write_text("{broken", encoding="utf-8")
        assert config.kaggle_status()["username"] == ""
