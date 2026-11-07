import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "lint"))
import flywheel  # noqa: E402


class VerdictTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(flywheel.verdict('{"01": "X", "02": "Y", "03": "tie"}'),
                         {"01": "X", "02": "Y", "03": "tie"})

    def test_lowercase_and_spaces_in_values(self):
        self.assertEqual(flywheel.verdict('{"01":"x ", "02":" y"}'), {"01": "X", "02": "Y"})

    def test_keys_without_leading_zero(self):
        self.assertEqual(flywheel.verdict('{"1": "X", "12": "Y"}'), {"01": "X", "12": "Y"})

    def test_other_values_become_tie(self):
        self.assertEqual(flywheel.verdict('{"01": "동점", "02": "모름", "03": ""}'),
                         {"01": "tie", "02": "tie", "03": "tie"})

    def test_reason_lines_around_json(self):
        text = "\n".join([
            "두 글을 비교했습니다.",
            '{"01": "x", "02": "Y"}',
            "이유: 01은 X 쪽이 숫자를 더 정확히 적었습니다.",
            "02는 Y 쪽 문단이 짧습니다.",
        ])
        self.assertEqual(flywheel.verdict(text), {"01": "X", "02": "Y"})

    def test_json_in_code_fence(self):
        fence = "`" * 3
        text = f'판정입니다.\n{fence}json\n{{\n  "01": "Y",\n  "02": "tie"\n}}\n{fence}\n이유는 위와 같습니다.'
        self.assertEqual(flywheel.verdict(text), {"01": "Y", "02": "tie"})

    def test_no_json_or_broken_json_gives_empty(self):
        self.assertEqual(flywheel.verdict("판정할 수 없습니다."), {})
        self.assertEqual(flywheel.verdict('{"01": "X", }'), {})


if __name__ == "__main__":
    unittest.main()
