"""File-mode pipeline runs, which need neither Resolve nor a network.

Timeline mode is not covered here: it cannot run without a live Resolve, and
the Resolve side is exercised by the probe scripts in ``scripts/``.
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
def run_file_mode(tmp_path, monkeypatch):
    """Call pipeline.run in file mode with a stubbed transcription backend."""
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
        settings = Settings(srt_dir=str(tmp_path / "srt"), audio_dir=str(tmp_path))
        for key, value in overrides.items():
            setattr(settings, key, value)
        return pipeline.run(settings, audio_source="file", audio_file=str(audio))

    return go


class TestFileMode:
    def test_writes_the_combined_and_split_files(self, run_file_mode):
        outcome = run_file_mode()
        for path in (outcome.combined_srt, outcome.en_srt, outcome.ar_srt):
            assert Path(path).is_file()
        assert outcome.en_cues == 2
        assert outcome.ar_cues == 1

    def test_preview_carries_the_cue_text_for_the_ui(self, run_file_mode):
        outcome = run_file_mode()
        assert len(outcome.preview) == outcome.combined_cues
        assert outcome.preview[0]["text"].startswith("Okay")
        # Arabic must survive the trip as Arabic, not as a translation.
        assert any("بدنا" in cue["text"] for cue in outcome.preview)
        assert not outcome.preview_truncated

    def test_preview_is_capped_so_a_long_timeline_stays_serialisable(
        self, run_file_mode, monkeypatch
    ):
        monkeypatch.setattr(pipeline, "PREVIEW_LIMIT", 2)
        outcome = run_file_mode()
        assert len(outcome.preview) == 2
        assert outcome.preview_truncated
        assert outcome.combined_cues == 3   # the files still hold everything

    def test_no_font_step_when_nothing_was_placed(self, run_file_mode):
        # font_hint tells the user which typeface to set on the subtitle track
        # Resolve just received. File mode places nothing, so there is no track
        # to style and the advice would be noise.
        outcome = run_file_mode(font_ar="Geeza Pro")
        assert outcome.font_hint == ""
        # And it never leaks into warnings, which are for things that went wrong.
        assert not any("Geeza Pro" in w for w in outcome.warnings)

    def test_file_mode_says_why_it_did_not_import(self, run_file_mode):
        outcome = run_file_mode()
        assert outcome.placed_cues == 0
        assert any("does not import" in w for w in outcome.warnings)

    def test_empty_transcription_raises_rather_than_writing_nothing(
        self, run_file_mode, monkeypatch
    ):
        monkeypatch.setattr(
            kaggle_runner, "transcribe",
            lambda path, **kw: kaggle_runner.RunResult([], {}, "", "", Path("."), 0.0),
        )
        with pytest.raises(RuntimeError, match="no usable cues"):
            run_file_mode()
