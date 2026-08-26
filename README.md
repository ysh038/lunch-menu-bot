# 점심메뉴 Slack 봇

`nlsomhansig` 인스타그램 계정의 오늘 점심 메뉴 이미지를 가져와 `#점심메뉴` Slack 채널에 자동 게시합니다.

## 동작 방식

1. Instaloader로 `nlsomhansig` 최신 게시물 확인
2. 오늘(KST) 올라온 게시물만 이미지 다운로드
3. Slack `files.upload_v2`로 채널에 업로드
4. GitHub Actions가 평일 10:00(KST)에 실행

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

GitHub Actions용 base64 인코딩:

```bash
base64 -i session | pbcopy
```

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

### 4. GitHub Secrets

Repository → Settings → Secrets and variables → Actions:

| Secret | 값 |
|--------|-----|
| `SLACK_BOT_TOKEN` | Slack Bot Token |
| `SLACK_CHANNEL_ID` | `#점심메뉴` 채널 ID |
| `INSTAGRAM_USERNAME` | 보조 인스타 계정명 |
| `INSTAGRAM_SESSION_B64` | `session` 파일 base64 인코딩 값 |

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env
# .env 값 채우기
python main.py
```

## GitHub Actions 수동 테스트

Actions 탭 → **Lunch Menu Bot** → **Run workflow**

## 스케줄

| KST | UTC cron | 설명 |
|-----|----------|------|
| 09:45 | `45 0 * * 1-5` | 평일 오전 실행 |

`state.json`으로 같은 게시물 중복 전송을 방지합니다.

## 주의사항

- `session`, `.env`, `state.json`, `downloads/`는 git에 올리지 마세요.
- 인스타 세션이 만료되면 로컬에서 `instaloader --login`으로 재생성 후 GitHub Secret을 업데이트하세요.
- Slack에서 `not_in_channel` 오류가 나면 봇이 채널에 초대되지 않은 상태입니다.
