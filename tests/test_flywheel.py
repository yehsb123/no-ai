import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

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


class LockTest(unittest.TestCase):
    """관리자 폴더를 임시 폴더로 바꿔 끼우고 부른다. 수집 서버와 claude 는 부르지 않는다."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        home = pathlib.Path(d.name)
        self.out = home / "no-ai-flywheel"
        self.out.mkdir()
        (home / "projects").mkdir()
        self.lock = self.out / "running.lock"
        self.addCleanup(mock.patch.stopall)
        for name, value in {"OUT": self.out, "CACHE": self.out / "cache.json", "STATE": self.out / "state.json",
                            "REPORT": self.out / "보고서.html", "CHECKED": self.out / "catchup-checked",
                            "EVAL": self.out / "eval", "EVAL_CSV": self.out / "eval" / "결과.csv",
                            "EVAL_LOG": self.out / "eval" / "오류.txt", "LOCK": self.lock}.items():
            mock.patch.object(flywheel, name, value).start()
        mock.patch.object(flywheel.talking, "PROJECTS", home / "projects").start()
        mock.patch.object(flywheel, "everyone", return_value=(None, "시험")).start()
        self.run_eval = mock.patch.object(flywheel, "run_eval", return_value=[]).start()

    def main(self, *args):
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "argv", ["flywheel.py", *args]), contextlib.redirect_stdout(out):
            flywheel.main()

    def hold(self, hours_ago=0):
        self.lock.write_text("1", encoding="utf-8")
        t = time.time() - hours_ago * 3600
        os.utime(self.lock, (t, t))

    def catchup(self):
        """밀린 보고서가 있는 상태로 catchup 을 부르고, 띄우려던 프로세스 수를 돌려준다."""
        (self.out / "state.json").write_text('{"updated": "2026-01-01"}', encoding="utf-8")
        with mock.patch.object(flywheel.subprocess, "Popen") as popen:
            flywheel.catchup()
        return popen.call_count

    def test_full_run_skips_while_locked(self):
        self.hold()
        self.main()
        self.assertFalse((self.out / "보고서.html").exists())
        self.assertTrue(self.lock.exists())

    def test_eval_run_skips_while_locked(self):
        self.hold()
        self.main("--eval")
        self.run_eval.assert_not_called()
        self.assertFalse((self.out / "보고서.html").exists())

    def test_full_run_holds_lock_and_releases_it(self):
        seen = []
        real = flywheel.report

        def spy(*a, **k):
            seen.append(self.lock.exists())
            return real(*a, **k)

        with mock.patch.object(flywheel, "report", side_effect=spy):
            self.main()
        self.assertEqual(seen, [True])
        self.assertTrue((self.out / "보고서.html").exists())
        self.assertFalse(self.lock.exists())

    def test_lock_removed_after_exception(self):
        with mock.patch.object(flywheel, "report", side_effect=RuntimeError("보고서 실패")):
            with self.assertRaises(RuntimeError):
                self.main()
        self.assertFalse(self.lock.exists())

    def test_stale_lock_is_ignored(self):
        self.hold(hours_ago=3)
        self.main()
        self.assertTrue((self.out / "보고서.html").exists())
        self.assertFalse(self.lock.exists())

    def test_catchup_does_not_spawn_while_locked(self):
        self.hold()
        self.assertEqual(self.catchup(), 0)

    def test_catchup_spawns_when_not_locked(self):
        self.assertEqual(self.catchup(), 1)

    def test_catchup_ignores_stale_lock(self):
        self.hold(hours_ago=3)
        self.assertEqual(self.catchup(), 1)


if __name__ == "__main__":
    unittest.main()
