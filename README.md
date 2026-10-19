# 점심메뉴 Slack 봇

`nlsomhansig` 인스타그램 계정의 오늘 점심 메뉴 이미지를 가져와 `#점심메뉴` Slack 채널에 자동 게시합니다.

## 동작 방식

1. Instaloader 세션으로 `nlsomhansig` 최신 게시물 확인
   - 웹 REST 피드(`/api/v1/feed/user/<username>/username/`)를 먼저 쓰고, 실패하면 Instaloader GraphQL로 재시도
   - GraphQL 게시물 쿼리는 2026-10부터 `feedback_required`로 막혀 있음
2. 오늘(KST) 올라온 게시물만 이미지 다운로드
3. Slack `files.upload_v2`로 채널에 업로드
4. 이 서버의 crontab이 평일 09:45(KST)에 실행 (GitHub Actions는 쓰지 않음)

## 사전 설정

### 1. Slack 앱

1. [api.slack.com/apps](https://api.slack.com/apps)에서 앱 생성
2. Bot Token Scopes 추가:
   - `chat:write`
   - `files:write`
   - `channels:read`
3. 워크스페이스에 설치 후 Bot Token (`xoxb-...`) 발급
4. `#점심메뉴` 채널 생성
5. 채널에서 `/invite @봇이름`으로 봇 초대
6. 채널 세부정보에서 채널 ID (`C...`) 복사

### 2. Instagram 세션

보조 인스타 계정으로 로그인 세션을 생성합니다.

```bash
pip install instaloader
instaloader --login=보조계정명 --sessionfile=session
```

성공하면 프로젝트 루트에 `session` 파일이 생성됩니다.

### 3. 로컬 환경변수

`.env.example`을 복사해 `.env`를 만듭니다.

```bash
cp .env.example .env
```

`.env` 예시:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C...
INSTAGRAM_USERNAME=보조계정명
TARGET_PROFILE=nlsomhansig
```

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env
# .env 값 채우기
python main.py
```

## 스케줄

서버(KST)의 crontab으로 평일 09:45에 실행하고, 출력은 `cron.log`에 쌓입니다.

```cron
45 9 * * 1-5 cd /home/mvldev/sanghoon/nlsomhansig && /home/mvldev/sanghoon/nlsomhansig/venv/bin/python main.py >> /home/mvldev/sanghoon/nlsomhansig/cron.log 2>&1
```

`state.json`으로 같은 게시물 중복 전송을 방지합니다. 같은 날 수동 실행 후 cron이 다시 돌아도 이미 보낸 게시물은 건너뜁니다.

## 주의사항

- `session`, `.env`, `state.json`, `downloads/`는 git에 올리지 마세요.
- 인스타 세션이 만료되면 서버에서 `venv/bin/instaloader --login=보조계정명 --sessionfile=session`으로 재생성하세요.
- Slack에서 `not_in_channel` 오류가 나면 봇이 채널에 초대되지 않은 상태입니다.
