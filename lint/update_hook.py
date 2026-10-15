"""SessionStart 훅. 설치한 PC가 새 규칙을 스스로 받게 한다.

Claude Code 기본 자동 업데이트는 직접 추가한 마켓플레이스에서 꺼져 있고, 마켓플레이스 쪽에서 켤 방법이 없다.
그래서 세션을 열 때 여섯 시간에 한 번 업데이트 명령을 뒤에서 돌린다. 받은 규칙은 다음 세션부터 적용된다.
세션 시작을 붙잡지 않도록 자기 자신을 뒤에서 다시 띄우고 바로 끝난다.

GitHub 에서 받은 마켓플레이스 사본은 업데이트 명령보다 먼저 원격 상태로 덮어쓴다. 저장소 기록을 다시 쓰면
업데이트 명령이 사본을 앞으로 감지 못해 그 PC가 옛 플러그인에 머물 수 있다. 관리자 PC처럼 폴더를
마켓플레이스로 등록한 경우는 원본이라 건드리지 않는다.

    python update_hook.py         훅으로 쓸 때
    python update_hook.py --now   지금 바로 받기
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

CLAUDE = pathlib.Path.home() / ".claude"
STAMP = CLAUDE / ".no-ai-updated"
EVERY = 6 * 60 * 60


def git(*args):
    try:
        return subprocess.run(["git", *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sync_marketplace():
    try:
        known = json.loads((CLAUDE / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
        entry = known["no-ai"]
    except (OSError, ValueError, KeyError):
        return
    if entry.get("source", {}).get("source") != "github":
        return
    where = entry.get("installLocation", "")
    if where and pathlib.Path(where, ".git").exists() and git("-C", where, "fetch", "-q", "origin"):
        git("-C", where, "reset", "-q", "--hard", "@{u}")


def update():
    claude = shutil.which("claude")
    if not claude:
        return
    sync_marketplace()
    for args in (["plugin", "marketplace", "update", "no-ai"], ["plugin", "update", "no-ai@no-ai"]):
        subprocess.run([claude, *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=300)


def main():
    if "--now" in sys.argv:
        update()
        return
    if STAMP.exists() and time.time() - STAMP.stat().st_mtime < EVERY:
        return
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.touch()
    flags = {}
    if os.name == "nt":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    subprocess.Popen([sys.executable, __file__, "--now"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)


if __name__ == "__main__":
    main()
