import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "lint"))
import noai_lint  # noqa: E402

FENCE = "`" * 3


def paras(text):
    return [p for _, p in noai_lint.paragraphs(noai_lint.prose_lines(text))]


def hit_ids(text, domain="공통"):
    return {h[1] for h in noai_lint.run(text, domain, noai_lint.load_rules())}


class ParagraphsTest(unittest.TestCase):
    def test_blank_line_heading_table_and_list_split_paragraphs(self):
        text = "\n".join([
            "# 제목",
            "첫 줄입니다.",
            "이어지는 줄입니다.",
            "",
            "둘째 문단입니다.",
            "| 칸 | 값 |",
            "- 목록 항목입니다.",
            "1. 번호 항목입니다.",
            "마지막 문단입니다.",
        ])
        self.assertEqual(paras(text), [
            "첫 줄입니다. 이어지는 줄입니다.",
            "둘째 문단입니다.",
            "목록 항목입니다.",
            "번호 항목입니다.",
            "마지막 문단입니다.",
        ])

    def test_paragraph_keeps_its_first_line_number(self):
        lines = noai_lint.prose_lines("\n\n셋째 줄에서 시작합니다.\n넷째 줄입니다.")
        self.assertEqual(noai_lint.paragraphs(lines), [(3, "셋째 줄에서 시작합니다. 넷째 줄입니다.")])

    def test_code_block_and_indented_lines_are_not_prose(self):
        text = "\n".join([
            "본문입니다.",
            FENCE,
            "코드 안의 글입니다.",
            FENCE,
            "    들여쓴 줄입니다.",
            "다시 본문입니다.",
        ])
        self.assertEqual(paras(text), ["본문입니다.", "다시 본문입니다."])

    def test_empty_text_has_no_paragraph(self):
        self.assertEqual(paras(""), [])


class SentenceCountTest(unittest.TestCase):
    def test_counts_sentence_endings(self):
        self.assertEqual(noai_lint.sentence_count("하나입니다. 둘입니다! 셋인가요? 넷입니다."), 4)

    def test_period_inside_number_is_not_an_ending(self):
        self.assertEqual(noai_lint.sentence_count("속도가 1.5배 빨라졌습니다."), 1)

    def test_quoted_sentences_are_not_counted(self):
        p = '그는 "괜찮습니다. 금방 끝납니다."라고 했습니다. 회의는 “다음 주에 합니다. 확정입니다.” 로 끝났습니다.'
        self.assertEqual(noai_lint.sentence_count(p), 2)

    def test_four_sentences_trigger_paragraph_length_check(self):
        self.assertIn("C29", hit_ids("하나입니다. 둘입니다. 셋입니다. 넷입니다."))
        self.assertNotIn("C29", hit_ids("하나입니다. 둘입니다. 셋입니다."))


class LoadRulesTest(unittest.TestCase):
    def test_repository_rules_load_with_checks_and_exceptions(self):
        by_id = {r["id"]: r for r in noai_lint.load_rules()}
        self.assertEqual(by_id["C29"]["domain"], "공통")
        self.assertEqual(by_id["C29"]["checks"], [("내장", "문단길이")])
        self.assertEqual(by_id["C29"]["except"], {"메신저"})
        self.assertEqual(by_id["C49"]["except"], {"메신저", "발표", "에세이"})
        self.assertEqual(by_id["G03"]["domain"], "고객")

    def test_parses_temporary_rule_folder_and_skips_fenced_headings(self):
        rule = "\n".join([
            "# 시험 규칙",
            "",
            "## X01 첫 규칙",
            "",
            "설명 문장입니다.",
            "",
            FENCE,
            "## X99 코드 블록 안의 제목",
            "검사: 줄 `무시`",
            FENCE,
            "",
            "검사: 줄 `금지어`",
            "검사: 제목 `요약$`",
            "제외: 메신저, 발표",
            "",
            "## X02 검사 없는 규칙",
            "",
            "검사 없이 읽기만 합니다.",
        ])
        with tempfile.TemporaryDirectory() as d:
            folder = pathlib.Path(d)
            (folder / "3-시험.md").write_text(rule, encoding="utf-8")
            old = noai_lint.RULES
            noai_lint.RULES = folder
            try:
                rules = noai_lint.load_rules()
            finally:
                noai_lint.RULES = old
        self.assertEqual([r["id"] for r in rules], ["X01", "X02"])
        self.assertEqual(rules[0]["domain"], "시험")
        self.assertEqual(rules[0]["checks"], [("줄", "금지어"), ("제목", "요약$")])
        self.assertEqual(rules[0]["except"], {"메신저", "발표"})
        self.assertEqual(rules[1]["checks"], [])
        self.assertEqual(rules[1]["except"], set())


class AppliesTest(unittest.TestCase):
    def rule(self, domain, exc=()):
        return {"id": "X01", "domain": domain, "except": set(exc), "checks": []}

    def test_common_rule_applies_to_every_domain(self):
        self.assertTrue(noai_lint.applies(self.rule("공통"), "고객"))
        self.assertTrue(noai_lint.applies(self.rule("공통"), "공통"))

    def test_domain_rule_applies_only_to_its_domain(self):
        self.assertTrue(noai_lint.applies(self.rule("고객"), "고객"))
        self.assertTrue(noai_lint.applies(self.rule("고객"), "화면, 고객"))
        self.assertFalse(noai_lint.applies(self.rule("고객"), "공통"))

    def test_excluded_domain_turns_rule_off_even_with_other_domains(self):
        r = self.rule("공통", ["메신저"])
        self.assertFalse(noai_lint.applies(r, "메신저"))
        self.assertFalse(noai_lint.applies(r, "고객,메신저"))
        self.assertTrue(noai_lint.applies(r, "고객"))

    def test_excluded_domain_skips_real_check(self):
        text = "하나입니다. 둘입니다. 셋입니다. 넷입니다."
        self.assertIn("C29", hit_ids(text, "공통"))
        self.assertNotIn("C29", hit_ids(text, "메신저"))


class ChecksTest(unittest.TestCase):
    def test_c02_allows_one_letter_abbreviations(self):
        self.assertNotIn("C02", hit_ids("초·중·고 학생 모두 신청할 수 있습니다."))

    def test_c02_catches_middle_dot_list(self):
        self.assertIn("C02", hit_ids("참고한 디자인 시스템은 Toss · Ant 입니다."))

    def test_c50_ignores_dama_followed_by_tomorrow(self):
        self.assertNotIn("C50", hit_ids("회의 내용을 메일에 담아 내일까지 보내겠습니다."))

    def test_c50_catches_damanaetda(self):
        self.assertIn("C50", hit_ids("고객 의견을 이번 판에 모두 담아냈다."))

    def test_c51_ignores_maturity_date(self):
        self.assertNotIn("C51", hit_ids("예금 만기가 도래했습니다."))

    def test_c52_ignores_plain_sentence_with_geugeotdo(self):
        self.assertNotIn("C52", hit_ids("일정이 빠듯하다는 의견이 있었습니다. 그것도 검토해 보겠습니다."))

    def test_c52_catches_inverted_tail(self):
        self.assertIn("C52", hit_ids("작업이 다 끝났습니다. 그것도 하루 만에."))

    def test_c09_catches_guess_ending(self):
        self.assertIn("C09", hit_ids("응답 속도가 개선될 것으로 보입니다."))
        self.assertIn("C09", hit_ids("새 대안을 찾고 있었던 것입니다."))
        self.assertNotIn("C09", hit_ids("응답 속도가 개선된다고 봅니다."))

    def test_c30_catches_gak_with_mada(self):
        self.assertIn("C30", hit_ids("각 단계마다 로그를 남깁니다."))
        self.assertNotIn("C30", hit_ids("각 팀이 일주일마다 보고합니다."))

    def test_c26_catches_anio_answer_word(self):
        self.assertIn("C26", hit_ids("예, 아니오로 답해 주세요."))
        self.assertNotIn("C26", hit_ids("예, 아니요로 답해 주세요."))
        self.assertNotIn("C26", hit_ids("그것은 내 책이 아니오.", "에세이"))

    def test_c08_catches_make_a_difference(self):
        self.assertIn("C08", hit_ids("작은 설정 하나가 큰 차이를 만듭니다."))
        self.assertNotIn("C08", hit_ids("설정에 따라 결과가 달라집니다."))

    def test_d04_catches_bold_only_line(self):
        self.assertIn("D04", hit_ids("**지금 상태**\n배포가 끝났습니다.", "대화"))
        self.assertNotIn("D04", hit_ids("**지금 상태**는 배포 완료입니다.", "대화"))

    def test_d04_bold_label_list_needs_three_lines_in_a_row(self):
        two = "- **성능:** 빨라졌습니다.\n- **비용:** 줄었습니다."
        three = two + "\n- **안정성:** 오류가 없습니다."
        broken = two + "\n\n- **안정성:** 오류가 없습니다."
        self.assertNotIn("D04", hit_ids(two, "대화"))
        self.assertNotIn("D04", hit_ids(broken, "대화"))
        hits = noai_lint.run(three, "대화", noai_lint.load_rules())
        self.assertIn((1, "D04", "답변의 겉치레", "굵은 라벨 목록 3줄"), hits)
        self.assertNotIn("D04", hit_ids(three, "공통"))


if __name__ == "__main__":
    unittest.main()
