"""UserPromptSubmit 훅. NO-AI 가 켜져 있으면 매 요청에 적용하라는 한 줄을 넣는다.

무엇을 하라는지는 적용.md 에만 적는다. 여기에 적으면 두 곳이 된다.

규칙이 올라오면 세션을 다시 열지 않아도 바로 쓰도록 공개 저장소를 ~/.claude/no-ai-live 에 받아 두고,
요청 때마다 다섯 분에 한 번 뒤에서 새 커밋을 받는다. 안내에는 그 사본의 적용.md 와 규칙 버전을 넣는다.
사본이 아직 없으면 설치된 플러그인 폴더를 가리킨다.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAUDE = pathlib.Path.home() / ".claude"
OFF = CLAUDE / ".no-ai-off"
LIVE = CLAUDE / "no-ai-live"
STAMP = CLAUDE / ".no-ai-pulled"
# 설치한 사람이 켜졌는지 모르고 지나가지 않도록 첫 요청 한 번만 답변 첫 줄에 알리게 한다.
WELCOMED = CLAUDE / ".no-ai-welcomed"
WELCOME = ("이 PC에서 NO-AI가 처음 쓰였다. 답변 첫 줄에 "
           "\"NO-AI가 켜져 있습니다. 끄려면 /no-ai:off, 다시 켜려면 /no-ai:on 을 입력합니다.\" "
           "한 줄을 그대로 쓰고 요청에 답한다.")
REPO = "https://github.com/yehsb123/no-ai.git"
EVERY = 5 * 60


def refresh():
    """새 커밋을 받는다. 요청을 붙잡지 않도록 뒤에서 돌린다."""
    if STAMP.exists() and time.time() - STAMP.stat().st_mtime < EVERY:
        return
    CLAUDE.mkdir(parents=True, exist_ok=True)
    STAMP.touch()
    if (LIVE / ".git").exists():
        cmd = ["git", "-C", str(LIVE), "pull", "-q", "--ff-only"]
    else:
        cmd = ["git", "clone", "-q", "--depth", "1", REPO, str(LIVE)]
    flags = {}
    if os.name == "nt":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **flags)
    except OSError:
        pass


def version(folder):
    try:
        r = subprocess.run(["git", "-C", str(folder), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    if OFF.exists():
        return
    refresh()
    base = LIVE if (LIVE / "적용.md").exists() else ROOT
    ver = version(base) if base == LIVE else ROOT.name
    # 안내에 "한국어로 답한다"가 없을 때 영어로 답한 세션이 있었다 (D09).
    msg = (f"NO-AI 켜짐, 규칙 버전 {ver}. 사용자에게 하는 답변은 한국어로만 쓴다. 한국어로 쓰는 글과 답변은 {base / '적용.md'} 를 따른다. "
           f"그 파일의 경로는 {base} 기준이다.")
    if not WELCOMED.exists():
        CLAUDE.mkdir(parents=True, exist_ok=True)
        WELCOMED.touch()
        msg += " " + WELCOME
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": msg}}))


if __name__ == "__main__":
    main()
