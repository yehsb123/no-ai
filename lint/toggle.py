"""NO-AI 스위치와 요청 기록 스위치.

    python toggle.py on | off | 상태
    python toggle.py log-on | log-off

`~/.claude/.no-ai-off` 가 있으면 규칙이 꺼진 상태다. 설치하자마자 켜진 상태로 쓰도록 꺼짐 표시만 둔다.
`~/.claude/.no-ai-log-on` 이 있으면 고친 규칙 번호를 기록한다. 기록은 동의한 사람만 켜도록 켜짐 표시를 둔다.
플러그인 폴더는 업데이트 때 바뀌므로 두 표시 모두 그 밖에 둔다.
"""
import pathlib
import sys

CLAUDE = pathlib.Path.home() / ".claude"
OFF = CLAUDE / ".no-ai-off"
LOG_ON = CLAUDE / ".no-ai-log-on"
LOG_DIR = CLAUDE / "no-ai-log"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    arg = (sys.argv[1] if len(sys.argv) > 1 else "상태").lower()
    CLAUDE.mkdir(parents=True, exist_ok=True)
    if arg == "on":
        OFF.unlink(missing_ok=True)
    elif arg == "off":
        OFF.touch()
    elif arg == "log-on":
        LOG_ON.touch()
        print(f"기록 켜짐. 고친 규칙 번호와 도메인만 {LOG_DIR} 에 날짜별로 쌓입니다. 글 내용은 남기지 않고 어디로도 보내지 않습니다.")
        return 0
    elif arg == "log-off":
        LOG_ON.unlink(missing_ok=True)
        print(f"기록 꺼짐. 이미 쌓인 기록은 {LOG_DIR} 에 남아 있습니다.")
        return 0
    elif arg != "상태":
        print("on, off, log-on, log-off 만 받습니다.")
        return 2
    print("NO-AI 꺼짐" if OFF.exists() else "NO-AI 켜짐")
    return 0


if __name__ == "__main__":
    sys.exit(main())
