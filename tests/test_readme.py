import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 예시를 더해도 README 의 숫자는 따라 바뀌지 않는다. 한 번 어긋나면 규칙 C34 를 가르치는
# 문서가 스스로 틀린 숫자를 들고 있게 되므로, 숫자를 적은 자리에서 바로 잡는다.
COUNT = re.compile(r"`examples` 폴더에 (\d+)개")


class ReadmeNumbers(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_예시_개수가_폴더와_같다(self):
        m = COUNT.search(self.readme)
        self.assertIsNotNone(m, "README 에 예시 개수를 적은 문장이 없습니다")
        real = len(list((ROOT / "examples").glob("*.md")))
        self.assertEqual(int(m.group(1)), real)


if __name__ == "__main__":
    unittest.main()
