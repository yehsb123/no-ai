"""PostToolUse 훅. 한국어 글을 .md 나 .txt 파일로 쓰면 바로 공통 규칙 자동 검사를 돌려 걸린 줄을 알린다.

안내는 요청마다 들어가지만 파일에 쓴 글은 아무도 검사하지 않았다. 막지는 않는다. 쓰는 쪽이 고칠지 정한다.
훅이 사용자 작업을 멈추면 안 되므로 입력이 깨졌거나 파일을 못 읽으면 아무것도 내보내지 않고 끝낸다.
"""
import json
import pathlib
import re
import sys

import guard
import noai_lint
import prompt_hook

SHOW = 10


def skipped(p):
    """규칙 저장소에는 일부러 나쁜 예가 있고, 받아 온 사본과 설치본은 사용자가 쓴 글이 아니다."""
    if p == guard.LIVE or guard.LIVE in p.parents or guard.PLUGINS in p.parents:
        return True
    return guard.repo_root(p) is not None


def notice(data):
    """알릴 글. 알릴 것이 없으면 None."""
    if prompt_hook.OFF.exists():
        return None
    raw = (data.get("tool_input") or {}).get("file_path") if isinstance(data, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    p = pathlib.Path(raw).resolve()
    if p.suffix.lower() not in (".md", ".txt") or skipped(p):
        return None
    try:
        text = p.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    if not re.search(r"[가-힣]", text):
        return None
    hits = noai_lint.run(text, "공통", noai_lint.load_rules())
    if not hits:
        return None
    lines = [f"{n}줄  {rid} {title}  [{got}]" for n, rid, title, got in hits[:SHOW]]
    if len(hits) > SHOW:
        lines.append(f"... {len(hits) - SHOW}건 더")
    return (f"방금 쓴 파일에서 걸린 규칙: {p} (공통 규칙 자동 검사 {len(hits)}건)\n" + "\n".join(lines)
            + f"\n도메인 규칙까지 보려면 python {pathlib.Path(noai_lint.__file__)} {p} --domain <도메인> 을 돌린다.")


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        msg = notice(data)
    except (UnicodeDecodeError, ValueError, OSError):
        return
    if msg:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": msg}}))


if __name__ == "__main__":
    main()
