"""PreToolUse 훅. NO-AI 규칙이 이 폴더 밖으로 복사되거나 폴더 안에 정해진 틀 밖의 파일이 생기지 않게 막는다.

규칙 사본이 바탕화면과 스킬 폴더 두 곳에 있던 때 한쪽만 고쳐져 어긋난 일이 있었다.
Bash 로 쓰는 파일은 여기서 못 막으므로 noai_lint.py --test 의 사본 검사가 뒤를 받친다.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED = [
    r"\.claude-plugin/(plugin|marketplace)\.json",
    r"hooks/hooks\.json",
    r"skills/(on|off)/SKILL\.md",
    r"적용\.md",
    r"README\.md",
    r"결정대기\.md",
    r"\.gitignore",
    r"rules/\d-[^/]+\.md",
    r"examples/예\d{2}-[^/]+\.md",
    r"lint/[^/]+\.py",
    r"inbox/[^/]+\.md",
    r"inbox/done/[^/]+\.md",
]


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    ti = data.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path")
    if not raw:
        return
    p = pathlib.Path(raw).resolve()
    try:
        rel = p.relative_to(ROOT).as_posix()
    except ValueError:
        rel = None
    if rel is None:
        if re.match(r"no-ai", p.name, re.I):
            deny(f"NO-AI 규칙은 {ROOT} 한 곳에만 둡니다. 사본을 만들지 말고 그 폴더의 rules/ 를 고칩니다.")
        return
    if not any(re.fullmatch(a, rel) for a in ALLOWED):
        deny(f"NO-AI 폴더에는 정해진 파일만 둡니다. {rel} 은 틀 밖입니다. 적용.md 의 파일 표를 봅니다.")


if __name__ == "__main__":
    main()
