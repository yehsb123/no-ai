"""UserPromptSubmit 훅.

NO-AI 가 켜져 있으면 매 요청에 적용하라는 한 줄을 넣는다. 무엇을 하라는지는 적용.md 에만 적는다.
기록을 켠 사람만 입력한 요청을 자기 PC 의 ~/.claude/no-ai-log 에 날짜별로 남긴다.
설치한 사람의 글이 모르게 밖으로 나가면 안 되므로 기록은 기본으로 꺼져 있고 어디로도 보내지 않는다.
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAUDE = pathlib.Path.home() / ".claude"
OFF = CLAUDE / ".no-ai-off"
LOG_ON = CLAUDE / ".no-ai-log-on"
LOG_DIR = CLAUDE / "no-ai-log"


def log(data):
    now = datetime.datetime.now()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {"time": now.isoformat(timespec="seconds"), "cwd": data.get("cwd"), "prompt": data.get("prompt")}
    with open(LOG_DIR / f"{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        data = {}
    if LOG_ON.exists() and data.get("prompt"):
        log(data)
    if not OFF.exists():
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"NO-AI 켜짐. 한국어로 쓰는 글과 답변은 {ROOT / '적용.md'} 를 따른다. 그 파일의 경로는 {ROOT} 기준이다.",
        }}))


if __name__ == "__main__":
    main()
