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
# 창 없는 예약 작업에서 git 이나 claude 를 부르면 Windows 에서 콘솔 창이 깜빡인다.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
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
                        "-p", "--", "rules"], capture_output=True, text=True, encoding="utf-8", errors="ignore",
                       **NO_WINDOW)
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


def rank(pending):
    """반영할 후보부터 위로 올린다. 점수를 매긴 이유도 함께 남겨 사람이 순서를 따져 볼 수 있게 한다.

    같은 세션에서 몇 시간 안에 지적이 되풀이되면 앞 지적을 덜 반영했다는 뜻이라(D02) 가장 크게 올린다.
    여러 지적에서 같은 규칙이 걸리면 그 규칙을 보강할 근거가 쌓인 것이라 함께 올린다.
    """
    def minutes(c):
        return datetime.datetime.fromisoformat(c["when"]).timestamp() / 60

    critics = [c for c in pending if c["sort"] == "지적"]
    for c in pending:
        score, why = (3, []) if c["sort"] == "지적" else (2, ["기준 예 후보"])
        again = sum(1 for o in critics if o is not c and o["session"] == c["session"]
                    and abs(minutes(o) - minutes(c)) <= 180)
        if again:
            score += 2 * min(again, 2)
            why.append(f"같은 세션 3시간 안 지적 {again}건 더")
        shared = Counter(rid for o in critics if o is not c for rid in o["hit"] if rid in c["hit"])
        if shared:
            rid, n = shared.most_common(1)[0]
            score += min(n, 3)
            why.append(f"{rid} 걸린 다른 지적 {n}건")
        c["score"], c["why"] = score, ", ".join(why)
    return sorted(pending, key=lambda c: (c["score"], c["when"]), reverse=True)


def report(days, cands, state, rules):
    titles = {r["id"]: r["title"] for r in rules}
    checked = {r["id"] for r in rules if r["checks"]}
    today = datetime.date.today().isoformat()
    week, prev = shift(today, -7), shift(today, -14)
    pending = rank([c for c in cands if c["when"] > state.get("done_until", "")])
    e = html.escape

    rows = []
    for c in pending:
        hit = ", ".join(c["hit"]) if c["hit"] else "검사에 안 걸림"
        rows.append(f"<tr><td>{c['score']}</td><td>{e(c['why'])}</td><td>{e(c['when'])}</td><td>{e(c['session'])}</td>"
                    f"<td>{c['sort']}</td><td>{e(c['user'])}</td><td class=ai>{e(c['ai'])}</td><td>{e(hit)}</td></tr>")

    # 지적받은 답변에서 자주 걸린 규칙은 문장이 약하거나 검사가 늦게 잡는 규칙이다.
    month = shift(today, -30)
    blamed = Counter(rid for c in cands if c["sort"] == "지적" and c["when"][:10] >= month for rid in c["hit"])
    brows = [f"<tr><td>{rid}</td><td>{e(titles.get(rid, ''))}</td><td>{n}</td></tr>" for rid, n in blamed.most_common(10)]

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
<p>점수가 높은 순서입니다. 지적은 3점, 칭찬은 2점에서 시작합니다. 같은 세션에서 3시간 안에 지적이 되풀이되면 1건마다 2점(최대 4점)을, 같은 규칙이 걸린 다른 지적이 있으면 1건마다 1점(최대 3점)을 더합니다.</p>
<p>마지막 칸은 그 반응 바로 앞 답변에서 자동 검사에 걸린 규칙입니다. 걸린 규칙이 있으면 규칙이 있는데 지키지 않은 것이고, 안 걸렸으면 새 규칙이나 검사 보강 후보입니다.</p>
{table(["점수", "점수 이유", "시각", "세션", "종류", "사용자 반응", "바로 앞 답변", "걸린 규칙"], rows, "쌓인 후보가 없습니다.")}
<h2>보강할 규칙</h2>
<p>최근 30일 동안 지적받은 답변에서 걸린 횟수입니다. 규칙이 있는데도 지적받았으니 문장이나 검사를 먼저 손볼 규칙입니다.</p>
{table(["규칙", "제목", "지적받은 답변 수"], brows, "최근 30일 동안 지적받은 답변에서 걸린 규칙이 없습니다.")}
<h2>정기 비교 시험</h2>
<p>매주 같은 요청 14개를 그때의 규칙으로 다시 쓰고, NO-AI 없이 쓴 고정 글과 어느 쪽인지 가린 채 비교합니다. 규칙 판정자는 NO-AI 규칙을 읽고, 실무 판정자는 규칙 없이 실무자 눈으로 고릅니다.</p>
{table(["날짜", "규칙 버전", "규칙 판정 NO-AI 우세", "없이 우세", "비슷함", "실무 판정 NO-AI 우세", "없이 우세", "비슷함", "자동 검사 NO-AI", "자동 검사 없이", "쓰기 실패"], eval_rows(), "아직 돌린 시험이 없습니다.")}
{f"<p>마지막 시험이 끝나지 못했습니다: {e(state['eval_error'])}. 자세한 내용은 eval/오류.txt 에 있습니다.</p>" if state.get("eval_error") else ""}
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


EVAL = OUT / "eval"
EVAL_CSV = EVAL / "결과.csv"
EVAL_LOG = EVAL / "오류.txt"
EVAL_COLS = ["날짜", "규칙버전", "A_noai", "A_plain", "A_tie", "B_noai", "B_plain", "B_tie", "검사_noai", "검사_plain", "실패"]
LIVE = pathlib.Path.home() / ".claude" / "no-ai-live"


def ask(prompt, tools="Read"):
    """훅, MCP, 스킬, 전역 CLAUDE.md, 메모리를 끄고 Claude 에게 한 번 묻는다. 실패하면 RuntimeError.

    전역 CLAUDE.md 에 NO-AI 요약 규칙이 있어, 켜 두면 실무 판정자도 규칙을 받은 채 고르고
    규칙 버전이 같아도 CLAUDE.md 를 고칠 때마다 점수가 움직인다. 규칙은 프롬프트에서 직접 읽게 한다.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--strict-mcp-config", "--disable-slash-commands",
           "--tools", tools, "--add-dir", str(LIVE), "--settings", '{"disableAllHooks":true}', "--no-session-persistence"]
    env = {**os.environ, "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                           timeout=900, cwd=str(EVAL), env=env, **NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"claude 실행 실패: {e}") from e
    try:
        d = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"claude 응답이 JSON 이 아님 (종료 코드 {r.returncode}): {r.stdout[:200]} {r.stderr[:200]}")
    if r.returncode != 0 or d.get("is_error") or not str(d.get("result", "")).strip():
        raise RuntimeError(f"claude 오류 (종료 코드 {r.returncode}): {str(d.get('result', ''))[:200]}")
    return d["result"]


def requests():
    """시험지의 (번호, 도메인, 요청 원문) 목록."""
    text = (EVAL / "requests.md").read_text(encoding="utf-8")
    out = []
    for block in re.split(r"(?m)^## ", text)[1:]:
        m = re.match(r"(\d{2}) .*\(도메인: ([^)]+)\)", block)
        if m:
            out.append((m[1], m[2], "## " + block.strip()))
    return out


def verdict(text):
    """판정 JSON 을 {"01": "X" | "Y" | "tie"} 로 맞춘다. 키 "1", 값 "x ", "동점" 같은 변형을 받는다."""
    m = re.search(r"\{[^{}]*\"0?1\"[^{}]*\}", text, re.S)
    try:
        raw = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    out = {}
    for k, v in raw.items():
        v = str(v).strip().upper()
        out[str(k).strip().zfill(2)] = v if v in ("X", "Y") else "tie"
    return out


def run_eval():
    """정기 비교 시험. 고정 글(baseline)은 그대로 두고 NO-AI 쪽만 지금 규칙으로 다시 쓴다.

    비교 대상이 매주 바뀌지 않아야 규칙이 나아졌는지 잴 수 있다.
    """
    import concurrent.futures
    import random
    reqs = requests()
    ver = subprocess.run(["git", "-C", str(LIVE), "rev-parse", "--short", "HEAD"], capture_output=True,
                         text=True, **NO_WINDOW).stdout.strip()
    day = datetime.date.today().isoformat()
    out = EVAL / day
    (out / "noai").mkdir(parents=True, exist_ok=True)
    writer = (f"한국어 글 하나를 쓴다. 먼저 {LIVE / '적용.md'} 를 읽고, 그 파일의 순서대로 규칙 파일을 읽고 따른다. "
              "검사 명령은 돌릴 수 없으니 규칙과 직접 대조한다. 아래 요청을 주어진 사실만으로 쓴다. "
              "사실에 없는 숫자, 이름, 기능, 약속은 지어내지 않는다. 쓴 글만 출력하고 설명은 붙이지 않는다.\n\n")
    def write(r):
        try:
            return ask(writer + r[2]).strip()
        except RuntimeError as e:
            log(f"{r[0]} 쓰기 실패: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        texts = dict(zip([n for n, _, _ in reqs], pool.map(write, reqs)))
    failed = [n for n, t in texts.items() if t is None]
    if len(failed) == len(reqs):
        raise RuntimeError("모든 글 쓰기에 실패했습니다")
    rules = noai_lint.load_rules()
    lint = {"noai": 0, "plain": 0}
    pairs, key = [], {}
    rnd = random.Random(day)
    for n, dom, req in reqs:
        if n in failed:
            continue
        noai, plain = texts[n], (EVAL / "baseline" / f"{n}.md").read_text(encoding="utf-8").strip()
        (out / "noai" / f"{n}.md").write_text(noai, encoding="utf-8")
        lint["noai"] += len(noai_lint.run(noai, dom, rules))
        lint["plain"] += len(noai_lint.run(plain, dom, rules))
        x, y = (noai, plain) if rnd.random() < 0.5 else (plain, noai)
        key[n] = {"X": "noai" if x is noai else "plain", "Y": "noai" if y is noai else "plain"}
        pairs.append(f"{req}\n\n### X\n\n{x}\n\n### Y\n\n{y}\n")
    blind = "\n\n".join(pairs)
    (out / "blind.md").write_text(blind, encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key), encoding="utf-8")
    # 비교할 글은 프롬프트에 넣지 않고 파일로 읽게 한다. Windows 명령 줄 길이 한도를 넘는다.
    form = (f'{out / "blind.md"} 에 요청마다 X, Y 두 글이 있다. 번호마다 더 나은 쪽을 고른다. '
            '답은 {"01": "X", "02": "tie", ...} 형식의 JSON 하나만 쓴다. 값은 X, Y, tie 가운데 하나다.')
    judges = {
        "A": f"{LIVE / 'rules'} 폴더의 규칙 파일을 모두 읽고, 그 규칙을 기준으로 두 글을 비교한다. 사실에 없는 내용을 지어낸 글은 진다. " + form,
        "B": "규칙 파일은 읽지 않는다. 그 글을 실제로 받아 쓰는 실무자 입장에서 더 바로 쓸 수 있는 글을 고른다. 사실에 없는 내용을 지어낸 글은 진다. " + form,
    }
    tally = {}
    for j, p in judges.items():
        v = verdict(ask(p))
        (out / f"verdict-{j}.json").write_text(json.dumps(v), encoding="utf-8")
        if set(v) != set(key):
            raise RuntimeError(f"판정자 {j} 의 답이 {len(v)}건이라 비교한 {len(key)}건과 맞지 않습니다")
        tally[j] = Counter(key[n][w] if w in ("X", "Y") else "tie" for n, w in v.items())
    row = [day, ver, tally["A"]["noai"], tally["A"]["plain"], tally["A"]["tie"],
           tally["B"]["noai"], tally["B"]["plain"], tally["B"]["tie"], lint["noai"], lint["plain"], len(failed)]
    lines = EVAL_CSV.read_text(encoding="utf-8").splitlines()[1:] if EVAL_CSV.exists() else []
    # 실패 칸이 생기기 전 행은 실패 0 으로 채운다.
    lines = [x if x.count(",") == len(EVAL_COLS) - 1 else x + ",0" for x in lines]
    lines.append(",".join(map(str, row)))
    EVAL_CSV.write_text(",".join(EVAL_COLS) + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return row


def log(msg):
    EVAL.mkdir(parents=True, exist_ok=True)
    with open(EVAL_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] {msg}\n")


def eval_rows():
    try:
        lines = EVAL_CSV.read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return []
    return ["<tr>" + "".join(f"<td>{html.escape(v)}</td>" for v in line.split(",")) + "</tr>"
            for line in reversed(lines[-12:])]


def main():
    # 예약 작업은 창 없는 pythonw 로 돌아 출력 대상이 없다.
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--done", action="store_true")
    ap.add_argument("--eval", action="store_true", help="정기 비교 시험을 돌린 뒤 보고서를 만든다")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.done:
        save_state(done_until=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M"), pending=0)
        print("쌓인 후보를 반영한 것으로 표시했습니다.")
        return
    if a.eval:
        # 시험이 실패해도 그날 보고서는 만든다. 창 없이 돌아 오류를 볼 곳이 파일뿐이다.
        try:
            row = run_eval()
            save_state(eval_error="")
            print("비교 시험:", dict(zip(EVAL_COLS, row)))
        except Exception as e:
            import traceback
            log(traceback.format_exc())
            save_state(eval_error=str(e)[:200])
            print("비교 시험 실패:", e)
    rules = noai_lint.load_rules()
    # 규칙이나 수집 기준이 바뀌면 같은 기록도 결과가 달라지므로 지난 결과를 버린다.
    basis = [(r["id"], r["domain"], r["checks"], sorted(r["except"])) for r in rules]
    code = b"".join(pathlib.Path(m.__file__).read_bytes() for m in (talking, noai_lint, sys.modules[__name__]))
    version = hashlib.sha1(json.dumps(basis).encode() + code).hexdigest()
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
    pending = report(days, cands, load(STATE, {}), rules)
    save_state(pending=pending, updated=datetime.date.today().isoformat())
    print(REPORT)
    print(f"반영 대기 후보 {pending}건, 답변 {sum(v['answers'] for v in days.values())}개 검사")


def save_state(**changes):
    """state.json 을 쓰기 직전에 다시 읽어 바뀐 칸만 고친다.

    시험이 길어져 매일 실행과 겹치거나 그사이 --done 이 끼어도 다른 실행이 쓴 값을 덮지 않는다.
    """
    state = load(STATE, {})
    state.update(changes)
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
