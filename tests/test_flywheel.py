import json
import os
import pathlib
import subprocess
import sys
import tempfile
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


class MajorityTest(unittest.TestCase):
    def test_two_to_one(self):
        self.assertEqual(flywheel.majority(["X", "Y", "X"]), "X")
        self.assertEqual(flywheel.majority(["tie", "Y", "Y"]), "Y")

    def test_all_different_is_tie(self):
        self.assertEqual(flywheel.majority(["X", "Y", "tie"]), "tie")


class CombineTest(unittest.TestCase):
    def test_majority_per_number_and_agreement(self):
        runs = [{"01": "X", "02": "Y", "03": "X", "04": "Y"},
                {"01": "X", "02": "X", "03": "Y", "04": "Y"},
                {"01": "X", "02": "tie", "03": "X", "04": "Y"}]
        final, agree = flywheel.combine(runs)
        self.assertEqual(final, {"01": "X", "02": "tie", "03": "X", "04": "Y"})
        self.assertEqual(agree, 50)


class FillTest(unittest.TestCase):
    def test_row_before_fail_column_gets_zero_and_blanks(self):
        row = ",".join(str(i) for i in range(10))
        self.assertEqual(flywheel.fill(row), row + ",0,,")

    def test_row_before_agreement_columns_gets_blanks(self):
        row = ",".join(str(i) for i in range(11))
        self.assertEqual(flywheel.fill(row), row + ",,")

    def test_full_row_is_unchanged(self):
        row = ",".join(str(i) for i in range(13))
        self.assertEqual(flywheel.fill(row), row)


def read_line(path, day="2026-11-01", sidechain=False):
    return json.dumps({"type": "assistant", "timestamp": f"{day}T03:00:00Z", "isSidechain": sidechain,
                       "message": {"content": [{"type": "tool_use", "name": "Read",
                                                "input": {"file_path": path}}]}}, ensure_ascii=False)


class RuleReadsTest(unittest.TestCase):
    def reads(self, *lines):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        f = pathlib.Path(d.name) / "s.jsonl"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return flywheel.rule_reads(str(f))

    def test_windows_backslash_paths(self):
        self.assertEqual(self.reads(read_line(r"C:\Users\a\no-ai\적용.md", "2026-11-01"),
                                    read_line(r"C:\Users\a\.claude\no-ai-live\rules\1-공통.md", "2026-11-02")),
                         ["2026-11-01", "2026-11-02"])

    def test_installed_plugin_copy(self):
        base = r"C:\Users\a\.claude\plugins\cache\no-ai\no-ai\20bbda7ec002"
        self.assertEqual(self.reads(read_line(base + r"\적용.md", "2026-11-01"),
                                    read_line("/home/a/.claude/plugins/cache/no-ai/no-ai/1.2.0/rules/2-글.md",
                                              "2026-11-02")),
                         ["2026-11-01", "2026-11-02"])

    def test_worktree_and_examples_are_not_counted(self):
        self.assertEqual(self.reads(read_line(r"C:\Users\a\no-ai\.claude\worktrees\w1\적용.md"),
                                    read_line(r"C:\Users\a\no-ai\.claude\worktrees\w1\rules\1-공통.md"),
                                    read_line(r"C:\Users\a\no-ai\examples\rules\1-공통.md")),
                         [])

    def test_sidechain_read_is_not_counted(self):
        self.assertEqual(self.reads(read_line(r"C:\Users\a\no-ai\적용.md", "2026-11-01", sidechain=True),
                                    read_line(r"C:\Users\a\no-ai\적용.md", "2026-11-02")),
                         ["2026-11-02"])


SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "lint" / "flywheel.py"


class CatchupWithoutAdminFolderTest(unittest.TestCase):
    def test_returns_at_once_and_leaves_nothing(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        env = {**os.environ, "HOME": d.name, "USERPROFILE": d.name}
        r = subprocess.run([sys.executable, str(SCRIPT), "--catchup"], env=env, capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "ignore"))
        self.assertEqual(list(pathlib.Path(d.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
