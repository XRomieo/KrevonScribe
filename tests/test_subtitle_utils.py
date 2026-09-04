import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool.subtitle_utils import (  # noqa: E402
    LANG_AR,
    LANG_EN,
    Cue,
    arabic_ratio,
    classify,
    cues_from_segments,
    format_timestamp,
    is_arabic_char,
    load_segments,
    render_srt,
    split_by_language,
    write_srt,
)


class TestArabicDetection:
    def test_detects_arabic_letters(self):
        assert is_arabic_char("ع")
        assert is_arabic_char("م")

    def test_rejects_latin_and_punctuation(self):
        assert not is_arabic_char("a")
        assert not is_arabic_char(" ")
        assert not is_arabic_char("?")

    def test_presentation_forms_count_as_arabic(self):
        assert is_arabic_char("ﻮ")  # Arabic Presentation Forms-B

    def test_pure_english_ratio_is_zero(self):
        assert arabic_ratio("Hello there") == 0.0

    def test_pure_arabic_ratio_is_one(self):
        assert arabic_ratio("مرحبا بك") == 1.0

    def test_punctuation_and_digits_do_not_skew_ratio(self):
        # Only the letters count, so this stays fully English.
        assert arabic_ratio("Hello, world! 123 -- ok?") == 0.0

    def test_numeric_only_cue_is_not_arabic(self):
        assert arabic_ratio("123 456") == 0.0
        assert classify("123 456") == LANG_EN

    def test_arabic_indic_digits_do_not_force_arabic(self):
        # Digits are script-neutral; the letters here are all Latin.
        assert classify("Take ٧ steps") == LANG_EN


class TestClassify:
    def test_routes_by_majority_script(self):
        assert classify("Hello this is an English line") == LANG_EN
        assert classify("مرحبا هذا سطر عربي") == LANG_AR

    def test_mostly_english_with_one_arabic_word_stays_english(self):
        assert classify("Mixed line with عربي inside") == LANG_EN

    def test_mostly_arabic_with_one_english_word_goes_arabic(self):
        assert classify("مرحبا بك في hello العالم العربي") == LANG_AR

    def test_threshold_zero_routes_any_arabic_to_arabic(self):
        assert classify("Mixed line with عربي inside", threshold=0.0) == LANG_AR

    def test_empty_text_is_english(self):
        assert classify("") == LANG_EN


class TestFormatTimestamp:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "00:00:00,000"),
            (0.5, "00:00:00,500"),
            (10.5, "00:00:10,500"),
            (61.25, "00:01:01,250"),
            (3661.001, "01:01:01,001"),
        ],
    )
    def test_formats(self, seconds, expected):
        assert format_timestamp(seconds) == expected

    def test_rounds_into_the_next_second_cleanly(self):
        # Must not produce a 4-digit millisecond field.
        assert format_timestamp(59.9999) == "00:01:00,000"

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            format_timestamp(-0.1)


class TestCue:
    def test_duration(self):
        assert Cue(1.0, 3.5, "hi").duration == pytest.approx(2.5)

    def test_rejects_reversed_times(self):
        with pytest.raises(ValueError):
            Cue(3.0, 1.0, "hi")

    def test_rejects_negative_start(self):
        with pytest.raises(ValueError):
            Cue(-1.0, 1.0, "hi")

    def test_zero_length_cue_allowed(self):
        assert Cue(2.0, 2.0, "hi").duration == 0.0


class TestSegments:
    def test_builds_cues_and_strips_whitespace(self):
        cues = cues_from_segments([{"start": 0.0, "end": 1.0, "text": "  hello  there "}])
        assert cues[0].text == "hello there"

    def test_drops_empty_segments(self):
        cues = cues_from_segments(
            [
                {"start": 0.0, "end": 1.0, "text": "   "},
                {"start": 1.0, "end": 2.0, "text": "real"},
            ]
        )
        assert [c.text for c in cues] == ["real"]

    def test_strips_bidi_and_zero_width_marks(self):
        cues = cues_from_segments(
            [{"start": 0.0, "end": 1.0, "text": "‏مرحبا‎​"}]
        )
        assert cues[0].text == "مرحبا"

    def test_load_segments_accepts_bare_list(self, tmp_path):
        p = tmp_path / "segments.json"
        p.write_text(json.dumps([{"start": 0, "end": 1, "text": "hi"}]), encoding="utf-8")
        assert [c.text for c in load_segments(p)] == ["hi"]

    def test_load_segments_accepts_wrapped_dict(self, tmp_path):
        p = tmp_path / "segments.json"
        p.write_text(
            json.dumps({"segments": [{"start": 0, "end": 1, "text": "hi"}]}),
            encoding="utf-8",
        )
        assert [c.text for c in load_segments(p)] == ["hi"]


class TestSplit:
    def test_every_cue_lands_in_exactly_one_bucket(self):
        cues = [
            Cue(0.5, 2.5, "Hello this is an English line"),
            Cue(3.0, 5.0, "مرحبا هذا سطر عربي"),
            Cue(5.5, 7.5, "Mixed line with عربي inside"),
        ]
        en, ar = split_by_language(cues)
        assert len(en) + len(ar) == len(cues)
        assert [c.text for c in ar] == ["مرحبا هذا سطر عربي"]
        assert len(en) == 2

    def test_empty_input(self):
        assert split_by_language([]) == ([], [])


class TestRenderSrt:
    def test_matches_expected_srt(self):
        out = render_srt([Cue(0.5, 2.5, "Hello"), Cue(3.0, 5.0, "World")])
        assert out == (
            "1\n00:00:00,500 --> 00:00:02,500\nHello\n"
            "\n"
            "2\n00:00:03,000 --> 00:00:05,000\nWorld\n"
        )

    def test_renumbers_and_sorts_by_start(self):
        out = render_srt([Cue(5.0, 6.0, "second"), Cue(1.0, 2.0, "first")])
        assert out.index("first") < out.index("second")
        assert out.startswith("1\n00:00:01,000")

    def test_offset_shifts_all_times(self):
        out = render_srt([Cue(0.5, 2.5, "Hello")], offset=10.0)
        assert "00:00:10,500 --> 00:00:12,500" in out

    def test_writes_utf8_with_arabic_intact(self, tmp_path):
        path = write_srt([Cue(0.0, 1.0, "مرحبا")], tmp_path / "out" / "ar.srt")
        assert path.read_text(encoding="utf-8").splitlines()[2] == "مرحبا"

    def test_empty_cue_list_produces_empty_file(self, tmp_path):
        path = write_srt([], tmp_path / "empty.srt")
        assert path.read_text(encoding="utf-8") == ""
