"""UserPromptSubmit 훅. NO-AI 가 켜져 있으면 매 요청에 적용하라는 한 줄을 넣는다.

무엇을 하라는지는 적용.md 에만 적는다. 여기에 적으면 두 곳이 된다.
요청 내용은 기록하지 않는다. 기록은 고친 규칙 번호만 남긴다(record.py).
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAUDE = pathlib.Path.home() / ".claude"
OFF = CLAUDE / ".no-ai-off"
LOG_ON = CLAUDE / ".no-ai-log-on"

if not OFF.exists():
    msg = f"NO-AI 켜짐. 한국어로 쓰는 글과 답변은 {ROOT / '적용.md'} 를 따른다. 그 파일의 경로는 {ROOT} 기준이다."
    if LOG_ON.exists():
        msg += " 기록 켜짐."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}))
