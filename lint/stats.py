"""NO-AI 사용 통계. 설치한 PC마다 하루 한 번 날짜별 숫자만 수집 서버로 보낸다.

    python stats.py          SessionStart 훅. 하루 한 번 뒤에서 --send 를 띄우고 바로 끝난다
    python stats.py --send   어제까지의 숫자를 모아 보낸다

플라이휠(flywheel.py)은 관리자 PC의 기록만 읽어 다른 PC에서 받은 지적과 칭찬을 볼 수 없었다.
그래서 모든 PC가 같은 기준(flywheel.scan)으로 센 숫자만 보내고, 관리자 보고서가 서버에서 모아 본다.

보내는 값은 익명 id, 규칙 사본 버전, 날짜마다 답변 수와 지적 수, 칭찬 수, 규칙 번호별 걸린 답변 수뿐이다.
대화 원문, 파일 경로, 프로젝트와 세션 이름은 이 PC 밖으로 나가지 않는다.
NO-AI 가 꺼져 있거나 ~/.claude/.no-ai-nostats 가 있으면 보내지 않는다.
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys

CLAUDE = pathlib.Path.home() / ".claude"
OFF = CLAUDE / ".no-ai-off"
NOSTATS = CLAUDE / ".no-ai-nostats"
DIR = CLAUDE / "no-ai-usage"
ID = DIR / "id"
STATE = DIR / "state.json"
CACHE = DIR / "cache.json"
STAMP = DIR / "ran"
# 환경변수는 실패 경로를 시험할 때 다른 주소를 가리키려고 둔다.
SERVER = os.environ.get("NO_AI_STATS_URL", "https://no-ai-stats.vercel.app")
# 첫 실행에 보낼 과거 날짜 수. 서버는 60일 안의 날짜만 받는다.
WINDOW = 45
# 서버가 20KB 넘는 본문을 받지 않아 날짜를 나눠 보낸다.
LIMIT = 18 * 1024


def disabled():
    return OFF.exists() or NOSTATS.exists()


def spawn():
    """세션 시작을 붙잡지 않도록 뒤에서 --send 를 띄운다. 하루 한 번만."""
    if disabled():
        return
    if STAMP.exists() and datetime.date.fromtimestamp(STAMP.stat().st_mtime) == datetime.date.today():
        return
    DIR.mkdir(parents=True, exist_ok=True)
    STAMP.touch()
    flags = {}
    if os.name == "nt":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, __file__, "--send"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    except OSError:
        STAMP.unlink(missing_ok=True)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def anon_id():
    import uuid
    try:
        old = ID.read_text(encoding="utf-8").strip()
        if uuid.UUID(old).version == 4 and str(uuid.UUID(old)) == old:
            return old
    except (OSError, ValueError):
        pass
    new = str(uuid.uuid4())
    ID.write_text(new, encoding="utf-8")
    return new


def numbers(scanned):
    """scan 결과에서 날짜별 숫자만 남긴다. 후보에 든 원문과 세션 이름은 여기서 버린다."""
    days = {d: {"answers": v["answers"], "critic": 0, "praise": 0, "hits": dict(v["hits"])}
            for d, v in scanned["days"].items()}
    for c in scanned["cands"]:
        day = days.setdefault(c["when"][:10], {"answers": 0, "critic": 0, "praise": 0, "hits": {}})
        day["critic" if c["sort"] == "지적" else "praise"] += 1
    return days


def collect(first, last):
    """first 부터 last 까지 날짜별 숫자. 활동이 없는 날은 뺀다."""
    import glob
    import flywheel
    import noai_lint
    import talking
    rules = noai_lint.load_rules()
    version = flywheel.basis(rules, talking, noai_lint, flywheel, sys.modules[__name__])
    cache = load(CACHE, {})
    if cache.get("version") != version:
        cache = {"version": version, "files": {}}
    # first 전에 마지막으로 고친 기록에는 보낼 날짜가 없다.
    since = datetime.datetime.combine(datetime.date.fromisoformat(first), datetime.time(),
                                      datetime.timezone.utc).timestamp()
    files = {}
    for f in glob.glob(str(talking.PROJECTS / "*" / "*.jsonl")):
        mtime = os.path.getmtime(f)
        if mtime < since:
            continue
        old = cache["files"].get(f)
        files[f] = old if old and old["mtime"] == mtime else {"mtime": mtime, "days": numbers(flywheel.scan(f, rules))}
    cache["files"] = files
    CACHE.write_text(json.dumps(cache), encoding="utf-8")

    total = {}
    for v in files.values():
        for d, x in v["days"].items():
            if not first <= d <= last:
                continue
            t = total.setdefault(d, {"answers": 0, "critic": 0, "praise": 0, "hits": {}})
            for k in ("answers", "critic", "praise"):
                t[k] += x[k]
            for rid, n in x["hits"].items():
                t["hits"][rid] = t["hits"].get(rid, 0) + n
    return {d: v for d, v in sorted(total.items()) if v["answers"] or v["critic"] or v["praise"]}


def chunks(base, days):
    """본문이 LIMIT 를 넘지 않게 날짜를 나눈다. 앞 묶음부터 보내야 실패한 날부터 다시 보낼 수 있다."""
    part = {}
    for d, v in days.items():
        if part and len(json.dumps({**base, "days": {**part, d: v}}).encode()) > LIMIT:
            yield part
            part = {}
        part[d] = v
    if part:
        yield part


def post(body):
    """2xx 면 None, 아니면 실패 이유."""
    # 훅은 1초 안에 끝나야 하는데 urllib 를 불러오는 데만 0.3초가 걸려 보낼 때 불러온다.
    import urllib.error
    import urllib.request
    req = urllib.request.Request(SERVER.rstrip("/") + "/api/report", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return None if 200 <= r.status < 300 else f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f"연결 실패 {e}"


def version():
    import prompt_hook
    live = prompt_hook.LIVE
    return (prompt_hook.version(live) if (live / ".git").exists() else "") or "설치본"


def send():
    if disabled():
        return
    DIR.mkdir(parents=True, exist_ok=True)
    state = load(STATE, {})
    # 기록의 시각이 UTC 라 날짜도 UTC 로 자른다. 오늘은 아직 끝나지 않아 어제까지만 보낸다.
    today = datetime.datetime.now(datetime.timezone.utc).date()
    yesterday = (today - datetime.timedelta(1)).isoformat()
    first = (today - datetime.timedelta(WINDOW)).isoformat()
    if state.get("last"):
        first = max(first, (datetime.date.fromisoformat(state["last"]) + datetime.timedelta(1)).isoformat())
    if first > yesterday:
        return
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    days = collect(first, yesterday)
    sent, error = None, None
    if days:
        base = {"id": anon_id(), "version": version()}
        for part in chunks(base, days):
            error = post({**base, "days": part})
            if error:
                break
            sent = max(part)
    # 활동이 없던 날은 보낼 것이 없으니 보낸 것으로 친다. 실패하면 마지막으로 받아 준 날까지만 올린다.
    last = yesterday if not error else (sent or state.get("last"))
    state.update(last=last, tried=datetime.datetime.now().isoformat(timespec="seconds"), error=error or "")
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def main():
    if "--send" in sys.argv:
        send()
    else:
        spawn()


if __name__ == "__main__":
    main()
