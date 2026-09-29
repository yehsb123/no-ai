# NO-AI

Claude Code가 한국어 글을 쓸 때 AI 티를 빼도록 하는 플러그인입니다. 설치하면 켜진 상태로 시작하고, 따로 명령을 치지 않아도 요청마다 규칙이 적용됩니다.

## 준비

- Claude Code가 설치되어 있어야 합니다.
- Python 3이 `python` 명령으로 실행되어야 합니다. Windows에서 Python을 설치할 때 첫 화면의 "Add python.exe to PATH"를 체크합니다.
- git이 설치되어 있어야 합니다. 공개 저장소라 GitHub 로그인은 필요 없습니다.

## 설치

터미널에서 아래 두 명령을 한 줄씩 따로 실행합니다. 첫 줄이 성공한 뒤 둘째 줄을 실행합니다.

```
claude plugin marketplace add yehsb123/no-ai
claude plugin install no-ai@no-ai
```

Claude Code 입력창에서 해도 됩니다. 그때는 `/plugin marketplace add yehsb123/no-ai` 를 보내고, 끝난 뒤 `/plugin install no-ai@no-ai` 를 따로 보냅니다. 두 줄을 한 번에 붙여 넣으면 한 명령으로 읽혀 설치되지 않습니다.

설치가 끝나면 Claude Code를 닫았다가 다시 엽니다. `/no-ai:on` 을 입력했을 때 "NO-AI 켜짐"이 나오면 설치된 상태입니다. 실패하면 터미널에 나온 오류 문구를 저장소 관리자에게 보냅니다.

## 업데이트 받기

규칙은 계속 고쳐집니다. 처음 한 번 자동 업데이트를 켜 둡니다.

1. 입력창에 `/plugin` 을 입력합니다.
2. Marketplaces 탭에서 no-ai를 고릅니다.
3. 자동 업데이트를 켭니다.

켜 두면 Claude Code를 시작할 때마다 새 규칙을 받습니다. 지금 바로 받으려면 `/plugin marketplace update no-ai` 를 입력합니다.

## 켜고 끄기

- `/no-ai:off` 로 끕니다.
- `/no-ai:on` 으로 다시 켭니다.

한 번 바꾸면 그 PC의 모든 세션에 적용됩니다.

## 규칙 제안

설치된 폴더의 규칙 파일은 고치지 않습니다. 다음 업데이트 때 원래대로 돌아갑니다. 새 규칙이 필요하면 고치기 전 문장, 고친 뒤 문장, 이유를 저장소 관리자에게 보냅니다.

## 지우기

`/plugin uninstall no-ai@no-ai` 를 입력합니다.
