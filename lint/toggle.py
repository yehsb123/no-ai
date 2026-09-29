"""NO-AI 스위치. `~/.claude/.no-ai-off` 가 있으면 꺼진 상태다.

설치하자마자 켜진 상태로 쓰도록 꺼짐 표시만 둔다. 플러그인 폴더는 업데이트 때 바뀌므로
표시는 그 밖에 둔다.

    python toggle.py on | off | 상태
"""
import pathlib
import sys

OFF = pathlib.Path.home() / ".claude" / ".no-ai-off"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    arg = (sys.argv[1] if len(sys.argv) > 1 else "상태").lower()
    if arg == "on":
        OFF.unlink(missing_ok=True)
    elif arg == "off":
        OFF.parent.mkdir(parents=True, exist_ok=True)
        OFF.touch()
    elif arg != "상태":
        print("on 또는 off만 받습니다.")
        return 2
    print("NO-AI 꺼짐" if OFF.exists() else "NO-AI 켜짐")
    return 0


if __name__ == "__main__":
    sys.exit(main())
