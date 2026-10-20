import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.jb_quickpanel.services import app_config


class CommandFailureLoggingTests(unittest.TestCase):
    def test_command_failure_log_records_diagnostic_context(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            app_config, "app_data_dir", return_value=Path(temp_dir)
        ):
            path = app_config.log_command_failure(
                "insert_style",
                "서식을 넣지 못했습니다.",
                context={"target_mode": "hwp", "selection": {"active": False}},
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn("command: insert_style", text)
        self.assertIn("서식을 넣지 못했습니다.", text)
        self.assertIn('"target_mode": "hwp"', text)

    def test_large_log_is_rotated_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            app_config, "app_data_dir", return_value=Path(temp_dir)
        ), patch.object(app_config, "MAX_CRASH_LOG_BYTES", 10):
            path = app_config.crash_log_path()
            path.write_text("old diagnostic data", encoding="utf-8")
            app_config.log_command_failure("status", "failed")

            previous = path.with_name("crash.previous.log")
            self.assertEqual(
                previous.read_text(encoding="utf-8"), "old diagnostic data"
            )
            self.assertIn("command: status", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
