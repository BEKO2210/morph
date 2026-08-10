import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morph.util import run_agent


class RetryOnTransientErrors(unittest.TestCase):
    def test_transient_error_is_retried_a_bounded_number_of_times(self):
        with tempfile.TemporaryDirectory() as td:
            counter = Path(td) / "attempts"
            cmd = [
                "bash", "-c",
                f"echo x >> {counter} && echo 'Connection reset by peer' && exit 1",
            ]
            with patch("morph.util.time.sleep"):
                result = run_agent(cmd, cwd=Path(td), timeout=5, retries=2, backoff_s=0.01, heartbeat_s=5)

            self.assertNotEqual(result.returncode, 0)
            attempts = counter.read_text().count("x")
            self.assertEqual(attempts, 3, "expected 1 initial attempt + 2 retries, got %d" % attempts)

    def test_non_transient_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as td:
            counter = Path(td) / "attempts"
            cmd = [
                "bash", "-c",
                f"echo x >> {counter} && echo 'the task you asked for is not possible' && exit 1",
            ]
            with patch("morph.util.time.sleep"):
                result = run_agent(cmd, cwd=Path(td), timeout=5, retries=2, backoff_s=0.01, heartbeat_s=5)

            self.assertNotEqual(result.returncode, 0)
            attempts = counter.read_text().count("x")
            self.assertEqual(attempts, 1, "a normal agent/task failure must never be retried")

    def test_success_on_second_attempt_stops_retrying(self):
        with tempfile.TemporaryDirectory() as td:
            counter = Path(td) / "attempts"
            cmd = [
                "bash", "-c",
                f"n=$(wc -l < {counter} 2>/dev/null || echo 0); echo x >> {counter}; "
                f"if [ \"$n\" -lt 1 ]; then echo 'Bad Gateway'; exit 1; else echo ok; exit 0; fi",
            ]
            with patch("morph.util.time.sleep"):
                result = run_agent(cmd, cwd=Path(td), timeout=5, retries=2, backoff_s=0.01, heartbeat_s=5)

            self.assertEqual(result.returncode, 0)
            attempts = counter.read_text().count("x")
            self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
