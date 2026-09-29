"""AI 슬롭을 고친 기록을 남긴다. 글 내용은 넣지 않고 도메인과 규칙 번호만 남긴다.

    python record.py --domain 고객 --fixed C01 C09 G03

기록을 켠 PC(`~/.claude/.no-ai-log-on`)에서만 쓴다. 꺼져 있으면 아무것도 하지 않는다.
"""
import argparse
import datetime
import json
import pathlib
import sys

CLAUDE = pathlib.Path.home() / ".claude"
LOG_ON = CLAUDE / ".no-ai-log-on"
LOG_DIR = CLAUDE / "no-ai-log"


def write(row):
    if not LOG_ON.exists():
        return False
    now = datetime.datetime.now()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {"time": now.isoformat(timespec="seconds"), **row}
    with open(LOG_DIR / f"{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--fixed", nargs="*", default=[])
    a = ap.parse_args()
    ok = write({"source": "self", "domain": a.domain, "fixed": sorted(set(a.fixed))})
    print("기록했습니다." if ok else "기록이 꺼져 있어 남기지 않았습니다.")


if __name__ == "__main__":
    main()
