"""NO-AI 규칙 검사기.

검사 패턴은 rules/*.md 의 `검사:` 줄에서 읽는다. 규칙 문장과 패턴이 한 곳에만 있어야
규칙을 고칠 때 검사기가 낡지 않는다. 테스트 샘플도 따로 두지 않고 examples/ 의
고치기 전, 고친 뒤 글을 그대로 쓴다.

    python noai_lint.py 글.md [--domain 고객]
    python noai_lint.py --stdin --domain 대화      붙여 넣은 글 검사
    python noai_lint.py --checklist 고객           자동 검사가 없는 규칙 번호와 제목
    python noai_lint.py --test                     예시 대조, 번호 중복, 문장 중복, 사본 경로
"""
import argparse
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = ROOT / "rules"
EXAMPLES = ROOT / "examples"
HOME = pathlib.Path(os.path.expanduser("~"))

HEAD = re.compile(r"^## ([A-Z]\d{2}) (.+)$")
CHECK = re.compile(r"^검사: (줄|제목|내장) `(.+)`$")
EXCEPT = re.compile(r"^제외: (.+)$")

# 규칙 원본은 이 폴더 하나다. 예전에 사본이 있던 곳에 다시 생기면 --test 가 실패한다.
FORBIDDEN_COPIES = [
    HOME / "Desktop" / "NO-AI.md",
    pathlib.Path("D:/Claude-기록/NO-AI.md"),
    ROOT / "NO-AI-rules.md",
    HOME / ".claude" / "skills" / "NO-AI" / "SKILL.md",
]


def load_rules():
    rules = []
    for f in sorted(RULES.glob("*.md")):
        cur = None
        fence = False
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("```"):
                fence = not fence
            if fence:
                continue
            m = HEAD.match(line)
            if m:
                cur = {"id": m[1], "title": m[2], "domain": f.stem.split("-", 1)[1],
                       "checks": [], "except": set()}
                rules.append(cur)
                continue
            if not cur:
                continue
            m = CHECK.match(line)
            if m:
                cur["checks"].append((m[1], m[2]))
            m = EXCEPT.match(line)
            if m:
                cur["except"] = {d.strip() for d in m[1].split(",")}
    return rules


def applies(rule, domain):
    if domain in rule["except"]:
        return False
    return rule["domain"] in ("공통", domain)


def prose_lines(text):
    """코드 블록, 들여쓴 줄, 인라인 코드를 뺀 (줄 번호, 줄) 목록."""
    out = []
    fence = False
    lines = text.splitlines()
    # SKILL.md 같은 파일 맨 앞의 YAML 머리말은 글이 아니다.
    front = 0
    if lines and lines[0] == "---" and "---" in lines[1:]:
        front = lines[1:].index("---") + 2
    for i, line in enumerate(lines, 1):
        if i <= front:
            out.append((i, ""))
            continue
        if line.startswith("```") or line.startswith("~~~"):
            fence = not fence
            out.append((i, ""))
            continue
        if fence or line.startswith("    ") or line.startswith("\t"):
            out.append((i, ""))
            continue
        out.append((i, re.sub(r"`[^`]*`", "", line)))
    return out


def paragraphs(lines):
    """빈 줄, 제목, 표, 목록 항목으로 나눈 문단 (시작 줄 번호, 합친 글)."""
    paras, buf, start = [], [], None
    for i, line in lines:
        s = line.strip()
        item = re.match(r"^([-*+]|\d+\.)\s", s)
        if not s or s.startswith("#") or s.startswith("|") or item:
            if buf:
                paras.append((start, " ".join(buf)))
            buf, start = [], None
            if item:
                paras.append((i, s[item.end():]))
            continue
        if start is None:
            start = i
        buf.append(s)
    if buf:
        paras.append((start, " ".join(buf)))
    return paras


def sentence_count(p):
    # 따옴표 안의 인용은 문장 수에 넣지 않는다.
    p = re.sub(r'"[^"]*"|“[^”]*”', "", p)
    return len(re.findall(r"[.!?](?=\s|$)", p))


BUILTIN = {
    "굵게": lambda lines: [(n, "굵게 %d번" % c) for n, p in paragraphs(lines)
                          if (c := len(re.findall(r"\*\*[^*]+\*\*", p))) >= 2],
    "문단길이": lambda lines: [(n, "%d문장" % c) for n, p in paragraphs(lines)
                            if (c := sentence_count(p)) >= 4],
}


def run(text, domain, rules):
    lines = prose_lines(text)
    hits = []
    for r in rules:
        if not applies(r, domain):
            continue
        for kind, pat in r["checks"]:
            if kind == "내장":
                hits += [(n, r["id"], r["title"], msg) for n, msg in BUILTIN[pat](lines)]
                continue
            rx = re.compile(pat)
            for n, line in lines:
                if kind == "제목" and not line.lstrip().startswith("#"):
                    continue
                m = rx.search(line)
                if m:
                    hits.append((n, r["id"], r["title"], m.group(0)))
    return sorted(set(hits))


def cmd_lint(text, name, domain, rules):
    domains = {r["domain"] for r in rules}
    if domain not in domains:
        print(f"도메인 이름이 틀렸습니다: {domain}. 가능한 값: {', '.join(sorted(domains))}")
        return 2
    hits = run(text, domain, rules)
    for n, rid, title, got in hits:
        print(f"{name}:{n}  {rid} {title}  [{got}]")
    print(f"자동 검사 {len(hits)}건. 자동 검사가 없는 규칙은 --checklist {domain} 로 봅니다.")
    return 1 if hits else 0


def cmd_checklist(domain, rules):
    for r in rules:
        if applies(r, domain) and not r["checks"]:
            print(f"{r['id']} {r['title']}")
    return 0


def parse_example(text):
    """예시 파일의 도메인, 걸린 규칙, 고치기 전 글, 고친 뒤 글."""
    dom = re.search(r"^도메인: (\S+)$", text, re.M)
    ids = re.search(r"^걸린 규칙: (.+)$", text, re.M)
    blocks = re.findall(r"^## (고치기 전|고친 뒤)\n+```text\n(.*?)\n```", text, re.M | re.S)
    b = dict(blocks)
    if not (dom and ids and "고치기 전" in b and "고친 뒤" in b):
        return None
    return dom[1], set(ids[1].split()), b["고치기 전"], b["고친 뒤"]


def sentences(text):
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    for line in text.splitlines():
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = re.sub(r"[\s`|*#>-]+", " ", s).strip()
            if len(s) >= 25:
                yield s


def cmd_test(rules):
    bad = []
    by_id = {r["id"]: r for r in rules}

    ids = [r["id"] for r in rules]
    for i in sorted({i for i in ids if ids.count(i) > 1}):
        bad.append(f"번호 중복: {i}")

    for f in sorted(EXAMPLES.glob("*.md")):
        ex = parse_example(f.read_text(encoding="utf-8"))
        if not ex:
            bad.append(f"예시 형식 틀림: {f.name}")
            continue
        dom, named, before, after = ex
        unknown = named - set(by_id)
        if unknown:
            bad.append(f"{f.name}: 없는 규칙 번호 {sorted(unknown)}")
        # 자동 검사는 규칙의 일부만 잡으므로, 걸린 규칙 목록 밖의 검출만 실패로 본다.
        extra = {h[1] for h in run(before, dom, rules)} - named
        if extra:
            bad.append(f"{f.name}: 걸린 규칙 목록에 없는 검출 {sorted(extra)}")
        left = run(after, dom, rules)
        if left:
            bad.append(f"{f.name}: 고친 뒤에 남은 검사 {[(h[1], h[3]) for h in left]}")

    seen = {}
    files = sorted(RULES.glob("*.md")) + sorted(EXAMPLES.glob("*.md")) + sorted(ROOT.glob("skills/*/SKILL.md")) + [ROOT / "적용.md", ROOT / "README.md", ROOT / "결정대기.md"]
    for f in files:
        if not f.exists():
            continue
        name = f.relative_to(ROOT).as_posix()
        for s in sentences(f.read_text(encoding="utf-8")):
            if s in seen and seen[s] != name:
                bad.append(f"문장 중복: {seen[s]} 와 {name}: {s[:40]}")
            elif s in seen:
                bad.append(f"문장 중복: {name} 안에서: {s[:40]}")
            seen.setdefault(s, name)

    for p in FORBIDDEN_COPIES:
        if p.exists():
            bad.append(f"규칙 사본이 있습니다: {p}")

    for b in bad:
        print(b)
    n_ex = len(list(EXAMPLES.glob("*.md")))
    print(f"규칙 {len(rules)}개, 예시 {n_ex}개, 문제 {len(bad)}건")
    return 1 if bad else 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--domain", default="공통")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--checklist", metavar="DOMAIN")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    rules = load_rules()
    if a.test:
        return cmd_test(rules)
    if a.checklist:
        return cmd_checklist(a.checklist, rules)
    if a.stdin:
        return cmd_lint(sys.stdin.buffer.read().decode("utf-8"), "입력", a.domain, rules)
    if not a.path:
        ap.error("검사할 파일을 주거나 --stdin 을 씁니다")
    return cmd_lint(pathlib.Path(a.path).read_text(encoding="utf-8"), a.path, a.domain, rules)


if __name__ == "__main__":
    sys.exit(main())
