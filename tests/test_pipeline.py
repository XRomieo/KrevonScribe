"""The whole run, with the transcription backend stubbed out.

Nothing here needs a network, a GPU or a video editor: an audio file goes in,
subtitle files come out, and that is the entire product.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool import kaggle_runner, pipeline  # noqa: E402
from resolve_subtitle_tool.config import Settings  # noqa: E402

SEGMENTS = [
    {"start": 0.0, "end": 3.0, "text": "Okay, so now time for the chickens.", "language": "en"},
    {"start": 3.2, "end": 6.0, "text": "بدنا نحمل ال chickens", "language": "ar"},
    {"start": 6.2, "end": 9.0, "text": "Why? What's the secret?", "language": "en"},
]


@pytest.fixture
def run_pipeline(tmp_path, monkeypatch):
    """Call pipeline.run with a stubbed transcription backend."""
    audio = tmp_path / "take01.wav"
    audio.write_bytes(b"RIFF....WAVE")

    def fake_transcribe(path, **kwargs):
        return kaggle_runner.RunResult(
            segments=list(SEGMENTS), meta={"detected_language": "en"},
            kernel_ref="u/k", dataset_ref="u/d",
            output_dir=tmp_path, elapsed_seconds=1.0,
        )

    monkeypatch.setattr(kaggle_runner, "transcribe", fake_transcribe)

    def go(**overrides):
        settings = Settings(srt_dir=str(tmp_path / "srt"))
        for key, value in overrides.items():
            setattr(settings, key, value)
        return pipeline.run(settings, audio_file=str(audio))

    return go


class TestRun:
    def test_writes_the_combined_and_split_files(self, run_pipeline):
        outcome = run_pipeline()
        for path in (outcome.combined_srt, outcome.en_srt, outcome.ar_srt):
            assert Path(path).is_file()
        assert outcome.en_cues == 2
        assert outcome.ar_cues == 1

    def test_the_combined_file_holds_both_languages_in_time_order(self, run_pipeline):
        # This is the file people drag onto a timeline, so it is the one that
        # has to be right: every cue, once, in the order they were spoken.
        outcome = run_pipeline()
        text = Path(outcome.combined_srt).read_text(encoding="utf-8")
        assert "Okay, so now time for the chickens." in text
        assert "بدنا نحمل ال chickens" in text
        assert text.index("chickens.") < text.index("بدنا") < text.index("secret")
        assert outcome.combined_cues == 3

    def test_preview_carries_the_cue_text_for_the_ui(self, run_pipeline):
        outcome = run_pipeline()
        assert len(outcome.preview) == outcome.combined_cues
        assert outcome.preview[0]["text"].startswith("Okay")
        # Arabic must survive the trip as Arabic, not as a translation.
        assert any("بدنا" in cue["text"] for cue in outcome.preview)
        assert not outcome.preview_truncated

    def test_preview_is_capped_so_a_long_recording_stays_serialisable(
        self, run_pipeline, monkeypatch
    ):
        monkeypatch.setattr(pipeline, "PREVIEW_LIMIT", 2)
        outcome = run_pipeline()
        assert len(outcome.preview) == 2
        assert outcome.preview_truncated
        assert outcome.combined_cues == 3   # the files still hold everything

    def test_a_clean_run_reports_nothing_to_warn_about(self, run_pipeline):
        assert run_pipeline().warnings == []

    def test_empty_transcription_raises_rather_than_writing_nothing(
        self, run_pipeline, monkeypatch
    ):
        monkeypatch.setattr(
            kaggle_runner, "transcribe",
            lambda path, **kw: kaggle_runner.RunResult([], {}, "", "", Path("."), 0.0),
        )
        with pytest.raises(RuntimeError, match="no usable cues"):
            run_pipeline()


class TestChoosingTheAudio:
    def test_no_file_is_a_clear_error_rather_than_a_crash(self, tmp_path):
        with pytest.raises(ValueError, match="Choose an audio file"):
            pipeline.run(Settings(srt_dir=str(tmp_path)), audio_file=None)

    def test_a_path_that_is_not_there_names_itself(self, tmp_path):
        missing = tmp_path / "gone.wav"
        with pytest.raises(FileNotFoundError, match="gone.wav"):
            pipeline.run(Settings(srt_dir=str(tmp_path)), audio_file=str(missing))
