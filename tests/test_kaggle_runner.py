import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool.kaggle_runner import (  # noqa: E402
    KERNEL_SOURCE, _status_error, _status_name, slugify,
)


class TestSlugify:
    def test_lowercases_and_hyphenates(self):
        assert slugify("Timeline Audio v2") == "timeline-audio-v2"

    def test_strips_unsafe_characters(self):
        assert slugify("EP04: Rough/Cut!!") == "ep04-rough-cut"

    def test_collapses_repeated_hyphens(self):
        assert "--" not in slugify("a   b___c")

    def test_pads_short_names_to_kaggle_minimum(self):
        # Kaggle rejects slugs shorter than 6 characters.
        assert len(slugify("ab")) >= 6

    def test_falls_back_when_nothing_usable_remains(self):
        assert slugify("!!!") == "resolve-subs"

    def test_respects_the_50_character_ceiling(self):
        assert len(slugify("x" * 200)) <= 50

    def test_never_starts_or_ends_with_a_hyphen(self):
        s = slugify("--weird name--")
        assert not s.startswith("-") and not s.endswith("-")


class TestStatusNormalisation:
    def test_plain_dict(self):
        assert _status_name({"status": "complete"}) == "complete"

    def test_enum_style_string(self):
        assert _status_name({"status": "KernelWorkerStatus.ERROR"}) == "error"

    def test_bare_string(self):
        assert _status_name("RUNNING") == "running"

    def test_underscores_removed(self):
        assert _status_name({"status": "CANCEL_REQUESTED"}) == "cancelrequested"

    def test_object_attribute(self):
        class S:
            status = "Complete"
        assert _status_name(S()) == "complete"

    def test_error_message_extracted(self):
        assert _status_error({"failureMessage": "boom"}) == "boom"

    def test_missing_error_is_empty(self):
        assert _status_error({"status": "complete"}) == ""


def test_kernel_source_is_bundled_and_runnable():
    assert KERNEL_SOURCE.is_file()
    assert "faster_whisper" in KERNEL_SOURCE.read_text(encoding="utf-8")
