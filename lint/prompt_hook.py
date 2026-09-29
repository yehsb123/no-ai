"""UserPromptSubmit 훅. NO-AI 가 켜져 있으면 매 요청에 적용하라는 한 줄을 넣는다.

무엇을 하라는지는 적용.md 에만 적는다. 여기에 적으면 두 곳이 된다.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OFF = pathlib.Path.home() / ".claude" / ".no-ai-off"

if not OFF.exists():
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": f"NO-AI 켜짐. 한국어로 쓰는 글과 답변은 {ROOT / '적용.md'} 를 따른다. 그 파일의 경로는 {ROOT} 기준이다.",
    }}))
