import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morph.ui import classify, make_reporter, strip_ansi, supports_color


class FakeTTYStream(io.StringIO):
    def isatty(self):
        return True


class Classify(unittest.TestCase):
    def test_failure_wording_is_red(self):
        self.assertEqual(classify("Builder failed (g0-candidate-1): boom"), "red")
        self.assertEqual(classify("Run failed: boom"), "red")

    def test_success_wording_is_green(self):
        self.assertEqual(classify("Builder completed in 12s (g0-candidate-1) — 3 files changed"), "green")
        self.assertEqual(classify("Applied winner patch — 3 files"), "green")

    def test_heartbeat_and_retry_wording_is_yellow(self):
        self.assertEqual(classify("codex builder still running (25s elapsed)"), "yellow")
        self.assertEqual(classify("codex review hit a transient error, retrying in 5s (attempt 1/2)"), "yellow")

    def test_started_wording_is_blue(self):
        self.assertEqual(classify("Builder started (g0-candidate-1)"), "blue")

    def test_default_is_cyan(self):
        self.assertEqual(classify("Sensing repository"), "cyan")


class StripAnsi(unittest.TestCase):
    def test_removes_color_codes(self):
        colored = "\033[36m[MORPH]\033[0m \033[32mBuilder completed\033[0m"
        self.assertEqual(strip_ansi(colored), "[MORPH] Builder completed")


class SupportsColor(unittest.TestCase):
    def test_no_color_env_wins_even_on_a_tty(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(supports_color(FakeTTYStream()))

    def test_force_color_env_wins_even_off_a_tty(self):
        with patch.dict(os.environ, {"MORPH_FORCE_COLOR": "1"}, clear=False):
            os.environ.pop("NO_COLOR", None)
            self.assertTrue(supports_color(io.StringIO()))

    def test_plain_stream_without_overrides_has_no_color(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("NO_COLOR", "MORPH_FORCE_COLOR", "MORPH_NO_COLOR"):
                os.environ.pop(k, None)
            self.assertFalse(supports_color(io.StringIO()))

    def test_tty_without_no_color_has_color(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("NO_COLOR", "MORPH_FORCE_COLOR", "MORPH_NO_COLOR"):
                os.environ.pop(k, None)
            self.assertTrue(supports_color(FakeTTYStream()))


class ReporterOutput(unittest.TestCase):
    def test_non_tty_output_has_no_ansi_codes(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            stream = io.StringIO()  # not a TTY
            report = make_reporter(run_dir, stream=stream)
            report("Builder started (g0-candidate-1)")
            out = stream.getvalue()
            self.assertNotIn("\033[", out)
            self.assertIn("[MORPH] Builder started (g0-candidate-1)", out)

    def test_log_file_is_always_plain_even_when_forced_colored(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            stream = FakeTTYStream()
            with patch.dict(os.environ, {"MORPH_FORCE_COLOR": "1"}, clear=False):
                os.environ.pop("NO_COLOR", None)
                report = make_reporter(run_dir, stream=stream)
                report("Builder completed in 5s (g0-candidate-1) — 2 files changed")
                report("codex builder still running (20s elapsed)")

            # Live stream IS colorized...
            self.assertIn("\033[", stream.getvalue())
            # ...but the on-disk log never contains escape codes, so it
            # stays readable in a plain editor/`cat`/CI log viewer.
            log_text = (run_dir / "progress.log").read_text(encoding="utf-8")
            self.assertNotIn("\033[", log_text)
            self.assertIn("Builder completed in 5s (g0-candidate-1) — 2 files changed", log_text)
            self.assertIn("codex builder still running (20s elapsed)", log_text)

    def test_heartbeat_lines_use_carriage_return_when_colored(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            stream = FakeTTYStream()
            with patch.dict(os.environ, {"MORPH_FORCE_COLOR": "1"}, clear=False):
                os.environ.pop("NO_COLOR", None)
                report = make_reporter(run_dir, stream=stream)
                report("codex builder still running (20s elapsed)")
                report("codex builder still running (40s elapsed)")
            out = stream.getvalue()
            self.assertIn("\r", out)


if __name__ == "__main__":
    unittest.main()
