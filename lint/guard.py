"""PreToolUse 훅. NO-AI 규칙이 이 폴더 밖으로 복사되거나 폴더 안에 정해진 틀 밖의 파일이 생기지 않게 막는다.

규칙 사본이 바탕화면과 스킬 폴더 두 곳에 있던 때 한쪽만 고쳐져 어긋난 일이 있었다.
Bash 로 쓰는 파일은 여기서 못 막으므로 noai_lint.py --test 의 사본 검사가 뒤를 받친다.

이 훅은 설치된 사본 폴더에서 돌기 때문에 자기 폴더를 원본으로 볼 수 없다. 고치려는 파일의 상위 폴더에서
no-ai 마켓플레이스 파일을 찾아 그 폴더를 저장소로 본다. 원본 저장소든 제안용 fork 든 같은 틀을 지킨다.
"""
import json
import pathlib
import re
import sys

REPO = "GitHub yehsb123/no-ai"
# prompt_hook.py 가 공개 저장소를 받아 두는 곳. 받아 온 사본이라 고치면 다음 pull 과 어긋난다.
LIVE = (pathlib.Path.home() / ".claude" / "no-ai-live").resolve()
# 플러그인 설치본과 마켓플레이스 사본. 마켓플레이스 사본에는 .git 이 있어 원본처럼 보인다.
PLUGINS = (pathlib.Path.home() / ".claude" / "plugins").resolve()
ALLOWED = [
    r"\.claude-plugin/(plugin|marketplace)\.json",
    r"hooks/hooks\.json",
    r"skills/(on|off)/SKILL\.md",
    r"적용\.md",
    r"README\.md",
    r"LICENSE",
    r"결정대기\.md",
    r"\.gitignore",
    r"\.gitattributes",
    r"rules/\d{1,2}-[^/]+\.md",
    r"examples/예\d{2}-[^/]+\.md",
    r"lint/[^/]+\.py",
]


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def repo_root(p):
    """p 를 품은 no-ai 저장소 폴더. 없으면 None."""
    for d in [p, *p.parents]:
        m = d / ".claude-plugin" / "marketplace.json"
        if m.is_file():
            try:
                if json.loads(m.read_text(encoding="utf-8")).get("name") == "no-ai":
                    return d
            except (OSError, ValueError):
                pass
    return None


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return
    ti = data.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path")
    if not raw:
        return
    p = pathlib.Path(raw).resolve()
    if p == LIVE or LIVE in p.parents:
        deny("자동으로 받아 온 규칙 사본이라 고치지 않습니다. 원본 저장소에서 고치거나 규칙 제안으로 올립니다.")
    root = repo_root(p)
    if root is None:
        # 규칙 문서 사본만 막는다. 다른 프로젝트의 no-ai 로 시작하는 코드 파일까지 막지 않는다.
        if re.match(r"no-?ai", p.name, re.I) and p.suffix.lower() == ".md":
            deny(f"NO-AI 규칙은 {REPO} 저장소 한 곳에만 둡니다. 사본을 만들지 말고 그 저장소의 rules/ 를 고칩니다.")
        return
    rel = p.relative_to(root).as_posix()
    if not (root / ".git").exists() or PLUGINS in root.parents:
        deny("설치된 플러그인 사본이라 고치지 않습니다. 고친 내용은 다음 업데이트 때 사라집니다. 원본 저장소에서 고칩니다.")
    if not any(re.fullmatch(a, rel) for a in ALLOWED):
        deny(f"NO-AI 폴더에는 정해진 파일만 둡니다. {rel} 파일은 틀 밖입니다. 적용.md 의 파일 표를 봅니다.")


if __name__ == "__main__":
    main()
