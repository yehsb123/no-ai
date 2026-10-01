"""토킹용 추출기. 이 PC의 모든 Claude Code 세션 기록에서 글에 대한 사용자 반응과 바로 앞 답변을 뽑는다.

    python talking.py --since 2026-09-29 [--out 폴더]

세션마다 파일 하나로 나눠 쓰고 경로와 건수를 출력한다. 기록에는 고객사와 동료 이름이 섞여 있으므로
결과 폴더는 임시 폴더에 두고 저장소에 넣지 않는다.
"""
import argparse
import datetime
import glob
import json
import os
import pathlib
import re
import sys
import tempfile

PROJECTS = pathlib.Path.home() / ".claude" / "projects"

# 글을 두고 한 반응만 남기는 거름망. 지적과 칭찬 양쪽 말을 넣었다.
WRITING = re.compile(
    r"말투|워딩|문구|표현|어색|슬롭|AI\s?(티|같|느낌)|톤|문장|제목|카피|이상하|이상해|별로|싫어|다시 ?써|"
    r"너무 ?길|길어|짧게|간결|쉽게|무슨 ?말|뭔 ?소리|이해가? 안|표로|굵게|이모지|기호|반복|중복|겹치|장황|"
    r"딱딱|번역투|자연스럽|사람이 쓴|맥락|명확|가독|헷갈|오해|좋아|좋네|좋다|완벽|맘에|마음에|최고|오지")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_noise(text):
    return (not text or text.startswith("<command-") or text.startswith("<local-command")
            or text.startswith("<system-reminder>") or text.startswith("[Request interrupted")
            or "<cross-session-message" in text[:300] or "tool_use_id" in text)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out")
    a = ap.parse_args()
    out = pathlib.Path(a.out or tempfile.mkdtemp(prefix="talking-"))
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    since_ts = datetime.datetime.strptime(a.since, "%Y-%m-%d").timestamp()
    for f in sorted(glob.glob(str(PROJECTS / "*" / "*.jsonl"))):
        # 그 날짜 뒤로 고쳐지지 않은 기록은 볼 필요가 없다.
        if os.path.getmtime(f) < since_ts:
            continue
        rows, last_ai, title = [], "", ""
        for line in open(f, encoding="utf-8", errors="ignore"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            title = d.get("customTitle") or title
            msg = d.get("message") or {}
            if d.get("type") == "assistant":
                t = text_of(msg.get("content"))
                if t.strip():
                    last_ai = t
            elif d.get("type") == "user" and not d.get("isMeta") and not d.get("isSidechain"):
                t = text_of(msg.get("content")).strip()
                when = d.get("timestamp", "")[:16]
                if is_noise(t) or when[:10] < a.since:
                    continue
                if WRITING.search(t):
                    rows.append((when, last_ai[-500:].replace("\n", " "), t[:1500]))
                last_ai = ""
        if not rows:
            continue
        name = re.sub(r"[^0-9A-Za-z가-힣_-]", "_", title or pathlib.Path(f).stem[:8])[:40]
        path = out / f"{len(rows):03d}-{name}-{pathlib.Path(f).stem[:8]}.txt"
        with open(path, "w", encoding="utf-8") as o:
            o.write(f"# 세션 {title or '(이름 없음)'} {pathlib.Path(f).stem}\n")
            for when, ai, user in rows:
                o.write(f"\n[{when}] AI: {ai}\n사용자: {user}\n")
        total += len(rows)
    print(f"{out}")
    print(f"반응 {total}건, 세션 파일 {len(list(out.glob('*.txt')))}개")


if __name__ == "__main__":
    main()
