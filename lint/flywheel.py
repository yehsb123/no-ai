"""NO-AI 플라이휠. 관리자 PC에서 매일 밤 돌아 규칙 후보와 규칙의 효과를 모은다.

    python flywheel.py          기록을 읽어 후보와 지표를 갱신하고 보고서를 만든다
    python flywheel.py --done   쌓인 후보를 규칙에 반영했다고 표시한다 (토킹이 끝난 뒤)

토킹을 잊으면 지적이 기록에만 쌓이고, 넣은 규칙이 효과가 있었는지는 아무도 재지 않았다.
그래서 수집과 정리와 측정은 매일 자동으로 하고, 규칙 반영만 사용자가 승인할 때 토킹으로 한다.
저장소가 공개라 잘못 뽑은 후보가 바로 모든 PC로 퍼지지 않게 하려는 것이다.

결과는 ~/.claude/no-ai-flywheel 에 둔다. 기록에 고객사와 동료 이름이 섞여 있어 저장소에 넣지 않는다.
기록 파일마다 고친 시각이 같으면 지난 결과를 다시 쓴다. 기록 전체가 수 GB라 매번 다 읽으면 몇 분이 걸린다.
"""
import argparse
import datetime
import glob
import hashlib
import html
import json
import os
import pathlib
import re
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import noai_lint  # noqa: E402
import talking  # noqa: E402

OUT = pathlib.Path.home() / ".claude" / "no-ai-flywheel"
CACHE = OUT / "cache.json"
STATE = OUT / "state.json"
REPORT = OUT / "보고서.html"
START = "2026-09-29"

# talking.WRITING 은 넓게 거른다. 후보에는 지적과 칭찬이 분명한 말만 남긴다.
# "꼼꼼하게 확실하게 명확하게" 같은 작업 지시는 둘 다 아니라 빠진다.
CRITIC = re.compile(r"슬롭|별론|별로(?=[야얍다네임인같에]|\s|$)|이상하|이상해|싫어|어색|뭔 ?소리|무슨 ?말|이해가? 안|헷갈|딱딱|번역투|장황|"
                    r"너무 ?길|띠꺼|맛없|AI ?(티|같|느낌)|가독성이? ?(떨어|안 ?좋|너무)|하지 ?마")
PRAISE = re.compile(r"좋아|좋네|좋다|굿|최고|오진다|오지네|오지는|맘에 ?들|마음에 ?들|훌륭")


def korean(t):
    hangul = len(re.findall(r"[가-힣]", t))
    return hangul >= 40 and hangul / max(len(t), 1) > 0.2


def scan(f, rules):
    """기록 파일 하나의 날짜별 답변 수, 규칙별 걸린 수, 후보."""
    title, events = talking.walk(f, START)
    days = defaultdict(lambda: {"answers": 0, "hits": Counter()})
    cands, last_ai = [], ""
    for kind, when, t in events:
        if kind == "ai":
            if when[:10] >= START and korean(t):
                day = days[when[:10]]
                day["answers"] += 1
                day["hits"].update({rid for _, rid, _, _ in noai_lint.run(t, "대화", rules)})
            last_ai = t
            continue
        sort = "지적" if CRITIC.search(t) else "칭찬" if PRAISE.search(t) else ""
        if sort and last_ai and korean(last_ai):
            hit = sorted({rid for _, rid, _, _ in noai_lint.run(last_ai, "대화", rules)})
            key = hashlib.sha1(f"{f}{when}{t[:80]}".encode()).hexdigest()[:12]
            cands.append({"id": key, "when": when, "session": title or pathlib.Path(f).stem[:8],
                          "sort": sort, "user": t[:600], "ai": last_ai[-600:], "hit": hit})
        last_ai = ""
    return {"days": {d: {"answers": v["answers"], "hits": dict(v["hits"])} for d, v in days.items()},
            "cands": cands}


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def added_dates():
    """규칙 번호마다 처음 들어간 날짜. 저장소 기록에서 찾는다."""
    root = noai_lint.ROOT
    r = subprocess.run(["git", "-C", str(root), "log", "--reverse", "--format=날짜 %ad", "--date=short",
                        "-p", "--", "rules"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    seen, day = {}, ""
    for line in r.stdout.splitlines():
        if line.startswith("날짜 "):
            day = line[3:]
        m = re.match(r"^\+## ([A-Z]\d{2}) ", line)
        if m and m[1] not in seen:
            seen[m[1]] = day
    return seen


def rate(days, rid, start, end):
    """start 이상 end 미만 날짜의 답변 100개당 걸린 수와 답변 수."""
    ans = sum(v["answers"] for d, v in days.items() if start <= d < end)
    hit = sum(v["hits"].get(rid, 0) for d, v in days.items() if start <= d < end)
    return (round(hit * 100 / ans, 1) if ans else None), ans


def shift(day, n):
    return (datetime.date.fromisoformat(day) + datetime.timedelta(days=n)).isoformat()


def report(days, cands, state, rules):
    titles = {r["id"]: r["title"] for r in rules}
    checked = {r["id"] for r in rules if r["checks"]}
    today = datetime.date.today().isoformat()
    week, prev = shift(today, -7), shift(today, -14)
    pending = [c for c in cands if c["when"] > state.get("done_until", "")]
    pending.sort(key=lambda c: c["when"], reverse=True)
    e = html.escape

    rows = []
    for c in pending:
        hit = ", ".join(c["hit"]) if c["hit"] else "검사에 안 걸림"
        rows.append(f"<tr><td>{e(c['when'])}</td><td>{e(c['session'])}</td><td>{c['sort']}</td>"
                    f"<td>{e(c['user'])}</td><td class=ai>{e(c['ai'])}</td><td>{e(hit)}</td></tr>")

    viol = []
    for rid in sorted(checked):
        now, n_now = rate(days, rid, week, shift(today, 1))
        before, _ = rate(days, rid, prev, week)
        if now:
            viol.append((now, rid, before, n_now))
    viol.sort(reverse=True)
    vrows = [f"<tr><td>{rid}</td><td>{e(titles[rid])}</td><td>{now}</td><td>{'' if b is None else b}</td></tr>"
             for now, rid, b, _ in viol[:20]]

    erows = []
    for rid, day in sorted(added_dates().items(), key=lambda x: x[1], reverse=True):
        if rid not in checked or day < shift(today, -60):
            continue
        b, nb = rate(days, rid, shift(day, -14), day)
        a, na = rate(days, rid, shift(day, 1), shift(day, 15))
        if nb and na:
            erows.append(f"<tr><td>{rid}</td><td>{e(titles.get(rid, ''))}</td><td>{day}</td><td>{b}</td><td>{a}</td></tr>")

    weekly = defaultdict(Counter)
    for c in cands:
        d = datetime.date.fromisoformat(c["when"][:10])
        weekly[(d - datetime.timedelta(days=d.weekday())).isoformat()][c["sort"]] += 1
    wrows = [f"<tr><td>{w} 주</td><td>{v['지적']}</td><td>{v['칭찬']}</td></tr>"
             for w, v in sorted(weekly.items(), reverse=True)[:8]]

    def table(head, body, empty):
        if not body:
            return f"<p>{empty}</p>"
        return "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + "".join(body) + "</table>"

    page = f"""<!doctype html><html lang=ko><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>NO-AI 플라이휠</title>
<style>
:root{{--bg:#fff;--fg:#111;--sub:#666;--line:#ddd}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--fg:#eee;--sub:#999;--line:#333}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:24px 16px;
word-break:keep-all;overflow-wrap:break-word}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:32px}} p{{color:var(--sub)}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
th{{color:var(--sub);font-weight:500}} td.ai{{color:var(--sub);font-size:12px}}
</style>
<h1>NO-AI 플라이휠</h1>
<p>{today} 갱신. "반영"이라고 하면 아래 후보를 원문과 대조해 규칙에 넣습니다.</p>
<h2>반영 대기 후보 {len(pending)}건</h2>
<p>오른쪽 칸은 그 반응 바로 앞 답변에서 자동 검사에 걸린 규칙입니다. 걸린 규칙이 있으면 규칙이 있는데 지키지 않은 것이고, 안 걸렸으면 새 규칙이나 검사 보강 후보입니다.</p>
{table(["시각", "세션", "종류", "사용자 반응", "바로 앞 답변", "걸린 규칙"], rows, "쌓인 후보가 없습니다.")}
<h2>자주 어기는 규칙</h2>
<p>답변 100개당 걸린 수입니다. 최근 7일과 그 전 7일을 나란히 둡니다.</p>
{table(["규칙", "제목", "최근 7일", "그 전 7일"], vrows, "최근 7일 동안 걸린 규칙이 없습니다.")}
<h2>새 규칙의 효과</h2>
<p>최근 60일 안에 넣은 규칙 가운데 자동 검사가 있는 것만 잽니다. 넣기 전 14일과 넣은 뒤 14일의 답변 100개당 걸린 수입니다.</p>
{table(["규칙", "제목", "넣은 날", "넣기 전", "넣은 뒤"], erows, "아직 잴 만큼 기록이 쌓인 규칙이 없습니다.")}
<h2>주마다 받은 지적과 칭찬</h2>
{table(["주", "지적", "칭찬"], wrows, "기록이 없습니다.")}
</html>
"""
    REPORT.write_text(page, encoding="utf-8")
    return len(pending)


def main():
    # 예약 작업은 창 없는 pythonw 로 돌아 출력 대상이 없다.
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--done", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    state = load(STATE, {})
    if a.done:
        state["done_until"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M")
        state["pending"] = 0
        STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        print("쌓인 후보를 반영한 것으로 표시했습니다.")
        return
    rules = noai_lint.load_rules()
    # 규칙이 바뀌면 같은 기록도 검사 결과가 달라지므로 지난 결과를 버린다.
    version = hashlib.sha1(json.dumps([(r["id"], r["checks"], sorted(r["except"])) for r in rules]).encode()).hexdigest()
    cache = load(CACHE, {})
    if cache.get("version") != version:
        cache = {"version": version, "files": {}}
    since = datetime.datetime.fromisoformat(START).timestamp()
    files = {}
    for f in glob.glob(str(talking.PROJECTS / "*" / "*.jsonl")):
        mtime = os.path.getmtime(f)
        if mtime < since:
            continue
        old = cache["files"].get(f)
        files[f] = old if old and old["mtime"] == mtime else {"mtime": mtime, **scan(f, rules)}
    cache["files"] = files
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    days = defaultdict(lambda: {"answers": 0, "hits": Counter()})
    cands = []
    for v in files.values():
        for d, x in v["days"].items():
            days[d]["answers"] += x["answers"]
            days[d]["hits"].update(x["hits"])
        cands += v["cands"]
    state["pending"] = report(days, cands, state, rules)
    state["updated"] = datetime.date.today().isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print(REPORT)
    print(f"반영 대기 후보 {state['pending']}건, 답변 {sum(v['answers'] for v in days.values())}개 검사")


if __name__ == "__main__":
    main()
