"""NO-AI 스위치. `~/.claude/.no-ai-off` 가 있으면 꺼진 상태다.

설치하자마자 켜진 상태로 쓰도록 꺼짐 표시만 둔다. 플러그인 폴더는 업데이트 때 바뀌므로
표시는 그 밖에 둔다.

    python toggle.py on | off | 상태
    python toggle.py notice     SessionStart 훅. 세션을 열 때 켜졌는지 화면에 보인다

마켓플레이스로 받은 사람이 꺼진 줄 알고 켜는 법을 찾은 일이 있어서, 세션마다 상태와 끄는 법을 먼저 보여 준다.
"""
import json
import pathlib
import sys

OFF = pathlib.Path.home() / ".claude" / ".no-ai-off"
# 관리자 PC에서만 생긴다. 플라이휠(flywheel.py)이 쌓인 규칙 후보 수를 적어 둔다.
FLYWHEEL = pathlib.Path.home() / ".claude" / "no-ai-flywheel" / "state.json"
NOSTATS = pathlib.Path.home() / ".claude" / ".no-ai-nostats"
# 사용 통계(stats.py)를 보낸다는 안내를 한 번 보였다는 표시.
STATS_NOTICE = pathlib.Path.home() / ".claude" / "no-ai-usage" / "notice-shown"


def pending():
    try:
        return int(json.loads(FLYWHEEL.read_text(encoding="utf-8")).get("pending", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    arg = (sys.argv[1] if len(sys.argv) > 1 else "상태").lower()
    if arg == "notice":
        msg = ("NO-AI가 꺼져 있습니다. 켜려면 /no-ai:on 을 입력합니다." if OFF.exists()
               else "NO-AI가 켜져 있습니다. 끄려면 /no-ai:off 를 입력합니다.")
        if n := pending():
            msg += f" 규칙 후보 {n}건이 쌓였습니다. \"반영\"이라고 하면 검토해서 넣습니다."
        if not OFF.exists() and not NOSTATS.exists() and not STATS_NOTICE.exists():
            msg += (" 규칙을 고치는 데 쓰려고 내일부터 하루 한 번 숫자 통계를 보냅니다. 답변 수, 규칙별로 걸린 수, 지적 수, 칭찬 수만 보내고"
                    " 대화 내용은 보내지 않습니다. 보내지 않으려면 사용자 폴더의 .claude 안에 .no-ai-nostats 파일을 만듭니다.")
            STATS_NOTICE.parent.mkdir(parents=True, exist_ok=True)
            STATS_NOTICE.touch()
        print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
        return 0
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
