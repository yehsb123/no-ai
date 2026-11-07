"""UserPromptSubmit 훅. NO-AI 가 켜져 있으면 매 요청에 적용하라는 한 줄을 넣는다.

무엇을 하라는지는 적용.md 에만 적는다. 여기에 적으면 두 곳이 된다.

규칙이 올라오면 세션을 다시 열지 않아도 바로 쓰도록 공개 저장소를 ~/.claude/no-ai-live 에 받아 두고,
요청 때마다 5분에 한 번 뒤에서 새 커밋을 받는다. 안내에는 그 사본의 적용.md 와 규칙 버전을 넣는다.
사본이 아직 없으면 설치된 플러그인 폴더를 가리킨다.

사본은 읽기 전용이라 받을 때 pull 대신 원격 상태로 덮어쓴다. 저장소 기록을 다시 쓰면 pull --ff-only 는
영영 실패하고 그 PC는 조용히 옛 규칙에 머문다. 덮어쓰기도 실패하면 지우고 새로 받는다.

    python prompt_hook.py          훅으로 쓸 때
    python prompt_hook.py --pull   사본 받기 (훅이 뒤에서 부른다)
"""
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAUDE = pathlib.Path.home() / ".claude"
OFF = CLAUDE / ".no-ai-off"
LIVE = CLAUDE / "no-ai-live"
STAMP = CLAUDE / ".no-ai-pulled"
REPO = "https://github.com/yehsb123/no-ai.git"
EVERY = 5 * 60


def refresh():
    """새 커밋을 받는다. 요청을 붙잡지 않도록 뒤에서 돌린다."""
    if STAMP.exists() and time.time() - STAMP.stat().st_mtime < EVERY:
        return
    CLAUDE.mkdir(parents=True, exist_ok=True)
    STAMP.touch()
    flags = {}
    if os.name == "nt":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, __file__, "--pull"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    except OSError:
        pass


# 콘솔 없이 뜬 프로세스가 git 을 부르면 Windows 에서 검은 창이 깜빡인다.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def git(*args):
    try:
        return subprocess.run(["git", *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=120, **NO_WINDOW).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def remove(folder):
    """Windows 의 git 객체 파일은 읽기 전용이라 그냥 지우면 남는다."""
    def writable(func, path, *_):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if not folder.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(folder, onexc=writable)
    else:
        shutil.rmtree(folder, onerror=writable)


def pull():
    if (LIVE / ".git").exists():
        if git("-C", str(LIVE), "fetch", "-q", "--depth", "1", "origin", "main"):
            if git("-C", str(LIVE), "reset", "-q", "--hard", "FETCH_HEAD"):
                return
        # 받지 못했을 때 사본이 멀쩡하면 인터넷 문제로 보고 있는 사본을 그대로 쓴다.
        elif git("-C", str(LIVE), "rev-parse", "-q", "--verify", "HEAD"):
            return
    try:
        remove(LIVE)
    except OSError:
        return
    git("clone", "-q", "--depth", "1", REPO, str(LIVE))


def version(folder):
    try:
        r = subprocess.run(["git", "-C", str(folder), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=3, **NO_WINDOW)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def rule_text(base):
    """규칙 파일을 모두 이어 붙인 글. 받는 중이라 반만 쓴 파일이 있어도 요청은 막지 않는다."""
    try:
        # autocrlf 로 받은 PC는 줄 끝이 \r\n 이다.
        return "\n".join(f.read_text(encoding="utf-8") for f in sorted((base / "rules").glob("*.md"))).replace("\r\n", "\n")
    except (OSError, ValueError):
        return ""


def head(text, rid):
    """규칙의 제목과 첫 문장. 문장은 규칙 파일에서 그때그때 읽어 두 곳에 적지 않는다."""
    r = re.search(rf"^## {rid} (.+)\n\n(.+?(?:[.](?=\s|$)|$))", text, re.M)
    return f"{rid} {r[1]}: {r[2]}" if r else ""


def listed(base):
    """적용.md 의 '자주 어기는 규칙' 줄에 적힌 번호들."""
    try:
        guide = (base / "적용.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, ValueError):
        return []
    m = re.search(r"^자주 어기는 규칙: (.+)$", guide, re.M)
    return re.findall(r"[A-Z]\d+", m[1]) if m else []


def often_broken(base, text=None):
    """'자주 어기는 규칙' 줄에 적힌 번호마다 규칙 첫 문장을 붙인다.

    규칙 파일을 가리키기만 하면 답변 때 다시 읽지 않아 같은 규칙을 계속 어겼다(플라이휠 측정, C49).
    """
    ids = listed(base)
    if not ids:
        return ""
    text = rule_text(base) if text is None else text
    out = [h for h in (head(text, rid) for rid in ids) if h]
    return " 답변마다 특히 지킨다. " + " / ".join(out) if out else ""


def common(text, skip=()):
    """공통 규칙(C)마다 첫 문장. 세션 대부분이 적용.md 를 열지 않고 답해(플라이휠 측정, 읽은 세션 0~17%)
    파일을 가리키는 것만으로는 규칙이 전해지지 않았다."""
    ids = sorted(set(re.findall(r"^## (C\d+) ", text, re.M)) - set(skip), key=lambda x: int(x[1:]))
    heads = [head(text, rid) for rid in ids]
    heads = [h for h in heads if h]
    return " 공통 규칙: " + " / ".join(heads) if heads else ""


def main():
    if "--pull" in sys.argv:
        pull()
        return
    if OFF.exists():
        return
    refresh()
    base = LIVE if (LIVE / "적용.md").exists() else ROOT
    ver = (version(base) if base == LIVE else "") or "설치본"
    # 안내에 "한국어로 답한다"가 없을 때 영어로 답한 세션이 있었다 (D09).
    msg = (f"NO-AI 켜짐, 규칙 버전 {ver}. 사용자에게 하는 답변은 한국어로만 쓴다. 한국어로 쓰는 글과 답변은 {base / '적용.md'} 를 따른다. "
           f"그 파일의 경로는 {base} 기준이다.")
    text = rule_text(base)
    # 특히 지킬 규칙은 앞에서 이미 보였으니 공통 목록에서 빼 같은 문장을 두 번 넣지 않는다.
    msg += often_broken(base, text) + common(text, listed(base))
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": msg}}))


if __name__ == "__main__":
    main()
