import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

LINT = pathlib.Path(__file__).resolve().parent.parent / "lint"
sys.path.insert(0, str(LINT))
import prompt_hook  # noqa: E402
import post_lint  # noqa: E402


def hook_output(argv, off):
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["prompt_hook.py", *argv]), \
            mock.patch.object(prompt_hook, "OFF", off), \
            mock.patch.object(prompt_hook, "refresh", lambda: None), \
            contextlib.redirect_stdout(out):
        prompt_hook.main()
    return out.getvalue()


class SubagentStartTest(unittest.TestCase):
    """서브에이전트는 UserPromptSubmit 을 거치지 않아 안내를 하나도 받지 못했다."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.off = pathlib.Path(d.name) / ".no-ai-off"

    def test_subagent_gets_same_context_under_its_own_event(self):
        prompt = json.loads(hook_output([], self.off))["hookSpecificOutput"]
        sub = json.loads(hook_output(["--subagent"], self.off))["hookSpecificOutput"]
        self.assertEqual(sub["hookEventName"], "SubagentStart")
        self.assertEqual(prompt["hookEventName"], "UserPromptSubmit")
        self.assertEqual(sub["additionalContext"], prompt["additionalContext"])
        self.assertIn("NO-AI 켜짐", sub["additionalContext"])

    def test_off_gives_nothing(self):
        self.off.touch()
        self.assertEqual(hook_output(["--subagent"], self.off), "")


class PostLintTest(unittest.TestCase):
    """파일에 쓴 글은 아무도 검사하지 않았다. 쓴 직후 걸린 규칙을 알린다."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = pathlib.Path(d.name)
        p = mock.patch.object(prompt_hook, "OFF", self.dir / ".no-ai-off")
        p.start()
        self.addCleanup(p.stop)

    def write(self, name, text):
        f = self.dir / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return f

    def notice(self, f):
        return post_lint.notice({"tool_name": "Write", "tool_input": {"file_path": str(f)}})

    def test_violation_in_markdown_is_reported(self):
        f = self.write("글.md", "# 제목\n\n이 기능은 빠릅니다 — 정말로 빠릅니다.\n")
        msg = self.notice(f)
        self.assertIsNotNone(msg)
        self.assertIn("방금 쓴 파일에서 걸린 규칙", msg)
        self.assertIn("—", msg)

    def test_clean_markdown_gives_nothing(self):
        self.assertIsNone(self.notice(self.write("글.md", "# 제목\n\n이 기능은 빠릅니다.\n")))

    def test_python_file_is_skipped(self):
        self.assertIsNone(self.notice(self.write("a.py", "# 이 기능은 빠릅니다 — 정말로.\n")))

    def test_file_without_hangul_is_skipped(self):
        self.assertIsNone(self.notice(self.write("a.md", "fast — really fast.\n")))

    def test_file_inside_no_ai_repo_is_skipped(self):
        repo = self.dir / "fork"
        self.write("fork/.claude-plugin/marketplace.json", json.dumps({"name": "no-ai"}))
        f = self.write("fork/rules/1-공통.md", "나쁜 예: 빠릅니다 — 정말로.\n")
        self.assertTrue(repo.is_dir())
        self.assertIsNone(self.notice(f))

    def test_off_skips(self):
        f = self.write("글.md", "빠릅니다 — 정말로.\n")
        (self.dir / ".no-ai-off").touch()
        self.assertIsNone(self.notice(f))

    def test_long_list_is_cut(self):
        f = self.write("글.md", "\n\n".join(f"{i}번 문장입니다 — 정말로." for i in range(30)) + "\n")
        msg = self.notice(f)
        self.assertLessEqual(sum(1 for line in msg.splitlines() if "[—]" in line), 10)
        self.assertIn("20건 더", msg)

    def test_missing_file_gives_nothing(self):
        self.assertIsNone(self.notice(self.dir / "없음.md"))

    def run_hook(self, stdin):
        # 이 PC에서 NO-AI 를 꺼 둔 상태여도 결과가 같도록 홈 폴더를 임시 폴더로 돌린다.
        env = {**os.environ, "HOME": str(self.dir), "USERPROFILE": str(self.dir)}
        return subprocess.run([sys.executable, str(LINT / "post_lint.py")], input=stdin,
                              capture_output=True, timeout=10, env=env)

    def test_broken_json_exits_zero_silently(self):
        r = self.run_hook(b"{not json")
        self.assertEqual((r.returncode, r.stdout), (0, b""))

    def test_hook_prints_post_tool_use_context(self):
        f = self.write("글.md", "빠릅니다 — 정말로.\n")
        r = self.run_hook(json.dumps({"tool_input": {"file_path": str(f)}}).encode("utf-8"))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        self.assertIn("—", out["additionalContext"])


if __name__ == "__main__":
    unittest.main()
