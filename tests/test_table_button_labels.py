import unittest

from src.jb_quickpanel.core.runtime import force_two_lines


class TableButtonLabelTests(unittest.TestCase):
    def test_keeps_single_line_input_phrase_together(self):
        self.assertEqual(force_two_lines("한 줄로 입력 설정"), "한 줄로\n입력 설정")
        self.assertEqual(force_two_lines("한 줄로 입력 해제"), "한 줄로\n입력 해제")


if __name__ == "__main__":
    unittest.main()
