"""PostToolUse 훅. 기록을 켠 PC에서 한국어 글 파일이 저장되면 자동 검사를 돌려 남은 규칙 번호만 기록한다.

AI가 스스로 적는 고친 기록(record.py)만으로는 빠뜨린 슬롭을 알 수 없어 저장된 결과도 함께 잰다.
파일 내용과 경로는 남기지 않고 확장자와 규칙 번호만 남긴다.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import noai_lint  # noqa: E402
import record  # noqa: E402

TEXT = {".md", ".txt", ".html"}


def main():
    if not record.LOG_ON.exists():
        return
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return
    raw = (data.get("tool_input") or {}).get("file_path")
    if not raw:
        return
    p = pathlib.Path(raw)
    if p.suffix.lower() not in TEXT or not p.exists():
        return
    text = p.read_text(encoding="utf-8", errors="ignore")
    if p.suffix.lower() == ".html":
        text = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S | re.I)
        text = re.sub(r"<h[1-6][^>]*>", "\n# ", text)
        text = re.sub(r"<[^>]+>", "\n", text)
    if not re.search(r"[가-힣]", text):
        return
    hits = noai_lint.run(text, "공통", noai_lint.load_rules())
    record.write({"source": "lint", "ext": p.suffix.lower(), "remaining": sorted({h[1] for h in hits})})


if __name__ == "__main__":
    main()
