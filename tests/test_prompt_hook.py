import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "lint"))
import prompt_hook  # noqa: E402

RULE_A = "# 공통\n\n## X01 첫 규칙\n\n첫 문장입니다. 둘째 문장은 빠집니다.\n\n## X02 둘째 규칙\n\n버전 1.5에서 바뀐 규칙입니다. 뒤 문장입니다.\n"
RULE_B = "# 고객\n\n## Y07 고객 규칙\n\n마침표 없이 끝나는 문장\n"


class OftenBrokenTest(unittest.TestCase):
    def make(self, guide, newline="\n"):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        base = pathlib.Path(d.name)
        (base / "rules").mkdir()
        (base / "rules" / "1-공통.md").write_bytes(RULE_A.replace("\n", newline).encode("utf-8"))
        (base / "rules" / "3-고객.md").write_bytes(RULE_B.replace("\n", newline).encode("utf-8"))
        (base / "적용.md").write_bytes(guide.replace("\n", newline).encode("utf-8"))
        return base

    def test_first_sentence_of_each_listed_rule(self):
        base = self.make("# 적용\n\n자주 어기는 규칙: X01, Y07, X02\n")
        self.assertEqual(
            prompt_hook.often_broken(base),
            " 답변마다 특히 지킨다. X01 첫 규칙: 첫 문장입니다. / Y07 고객 규칙: 마침표 없이 끝나는 문장"
            " / X02 둘째 규칙: 버전 1.5에서 바뀐 규칙입니다.",
        )

    def test_crlf_files_give_same_result(self):
        guide = "# 적용\n\n자주 어기는 규칙: X01\n"
        crlf = prompt_hook.often_broken(self.make(guide, "\r\n"))
        self.assertEqual(crlf, prompt_hook.often_broken(self.make(guide)))
        self.assertIn("X01 첫 규칙: 첫 문장입니다.", crlf)

    def test_unknown_rule_is_skipped(self):
        base = self.make("자주 어기는 규칙: Z99, X01\n")
        self.assertEqual(prompt_hook.often_broken(base), " 답변마다 특히 지킨다. X01 첫 규칙: 첫 문장입니다.")

    def test_no_line_or_no_known_rule_gives_empty(self):
        self.assertEqual(prompt_hook.often_broken(self.make("# 적용\n\n규칙 줄이 없습니다.\n")), "")
        self.assertEqual(prompt_hook.often_broken(self.make("자주 어기는 규칙: Z99\n")), "")

    def test_missing_folder_gives_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(prompt_hook.often_broken(pathlib.Path(d) / "없음"), "")


if __name__ == "__main__":
    unittest.main()


class CommonTest(unittest.TestCase):
    TEXT = ("## C02 가운뎃점\n\n가운뎃점을 쓰지 않는다. 뒤 문장.\n\n## C10 은어\n\n은어를 쓰지 않는다.\n\n"
            "## G01 고객\n\n고객 규칙이다.\n\n## C9 짧은 번호\n\n번호 순서를 본다.\n")

    def test_only_common_rules_in_number_order(self):
        self.assertEqual(prompt_hook.common(self.TEXT),
                         " 공통 규칙: C02 가운뎃점: 가운뎃점을 쓰지 않는다. / C9 짧은 번호: 번호 순서를 본다."
                         " / C10 은어: 은어를 쓰지 않는다.")

    def test_skipped_rules_are_left_out(self):
        self.assertNotIn("C02", prompt_hook.common(self.TEXT, ["C02"]))

    def test_no_common_rule_gives_empty(self):
        self.assertEqual(prompt_hook.common("## G01 고객\n\n고객 규칙이다.\n"), "")


class RepoRuleHeadTest(unittest.TestCase):
    """훅은 규칙마다 첫 문장만 보여 준다. 첫 줄이 표나 목록이면 지시가 전해지지 않는다."""

    def test_every_common_rule_opens_with_a_sentence(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        text = prompt_hook.rule_text(root)
        for rid in prompt_hook.re.findall(r"^## (C\d+) ", text, prompt_hook.re.M):
            h = prompt_hook.head(text, rid)
            body = h.split(": ", 1)[1] if h else ""
            self.assertTrue(body and not body.startswith(("|", " ")), f"{rid} 첫 줄이 지시 문장이 아닙니다: {body[:40]}")
