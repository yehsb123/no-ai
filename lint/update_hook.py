"""SessionStart 훅. 설치한 PC가 새 규칙을 스스로 받게 한다.

Claude Code 기본 자동 업데이트는 직접 추가한 마켓플레이스에서 꺼져 있고, 마켓플레이스 쪽에서 켤 방법이 없다.
그래서 세션을 열 때 여섯 시간에 한 번 업데이트 명령을 뒤에서 돌린다. 받은 규칙은 다음 세션부터 적용된다.
세션 시작을 붙잡지 않도록 자기 자신을 뒤에서 다시 띄우고 바로 끝난다.

    python update_hook.py         훅으로 쓸 때
    python update_hook.py --now   지금 바로 받기
"""
import os
import pathlib
import shutil
import subprocess
import sys
import time

STAMP = pathlib.Path.home() / ".claude" / ".no-ai-updated"
EVERY = 6 * 60 * 60


def update():
    claude = shutil.which("claude")
    if not claude:
        return
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
