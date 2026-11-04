# 점심메뉴 Slack 봇

식권 식당들이 네이버 플레이스 **소식** 탭에 올리는 오늘 메뉴판 사진을 가져와 Slack `#점심메뉴` 채널에 올린다.

| 식당 | 네이버 플레이스 |
|---|---|
| 하늘한정식뷔페 | [2089924926](https://map.naver.com/p/entry/place/2089924926) |
| 명인푸드한식뷔페 | [2099805786](https://map.naver.com/p/entry/place/2099805786) |

식당을 바꾸거나 추가하려면 `main.py`의 `RESTAURANTS`를 고친다.

## 동작 방식

1. 평일 09:00~12:00, 15분마다 두 식당의 소식 페이지(`pcmap.place.naver.com/restaurant/<ID>/feed`)를 읽는다.
   - 공식 API가 없어서 페이지에 내장된 `__APOLLO_STATE__` JSON을 읽는다. 로그인·쿠키가 필요 없다.
2. 오늘 날짜로 올라온 소식을 분류한다.
   - **메뉴**: 제목에 "메뉴"가 있고 이미지가 있음 → 이미지(긴 변 2048px로 축소)를 Slack에 업로드
   - **휴무**: 제목·본문에 "쉽니다", "휴무" 등이 있음 → 텍스트로 알림
   - 그 밖의 소식은 건너뛴다.
3. 이미 올린 소식(feedId)과 같은 이미지(URL)는 다시 올리지 않는다. 식당이 같은 글을 두 번 올리는 경우가 있다.
4. 첫 소식이 메뉴가 아닐 수 있어서, 메뉴를 올린 뒤에도 12:00까지 계속 확인한다. 하늘한정식뷔페는 11시 넘어 올리는 날도 있다.
5. 12:00 마지막 확인(`--final`)에서 메뉴도 휴무 글도 못 찾은 식당이 있으면 사유와 함께 알림을 한 번 보낸다.

토·일요일과 한국 공휴일(대체공휴일 포함)은 확인하지 않는다. 회사 휴무일 등은 `holidays_override.txt`에 `2026-12-24 off`처럼 적는다.

## 설정

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # SLACK_BOT_TOKEN, SLACK_CHANNEL_ID 채우기 (권한 600)
```

Slack 앱 Bot Token Scopes: `chat:write`, `files:write`. 봇을 `#점심메뉴` 채널에 초대해야 한다(`not_in_channel` 오류).

## 실행

```bash
venv/bin/python main.py                              # 한 번 확인
venv/bin/python main.py --final                      # 마지막 확인 + 미발견 알림
DRY_RUN=1 venv/bin/python main.py --date 2026-11-03  # Slack 없이 특정 날짜로 시험
venv/bin/python workday.py 2026-12-25                # 근무일 판단 확인
```

`DRY_RUN=1`이면 Slack에 보내지 않고 출력만 하며, 기록은 `state/dry_run/`에 따로 남긴다.

## 스케줄 (서버 crontab, KST)

```cron
*/15 9-11 * * 1-5 cd /home/mvldev/sanghoon/lunch-menu-bot && venv/bin/python main.py >> logs/cron.log 2>&1
0 12 * * 1-5 cd /home/mvldev/sanghoon/lunch-menu-bot && venv/bin/python main.py --final >> logs/cron.log 2>&1
```

## 파일

| 파일 | 역할 |
|---|---|
| `main.py` | 식당 목록, 소식 분류, 게시, 12:00 미발견 알림 |
| `naver_place.py` | 네이버 플레이스 소식 조회·파싱, 이미지 다운로드 |
| `slack_client.py` | Slack 업로드·메시지 |
| `state.py` | 하루 단위 게시 기록 `state/<날짜>.json` (파일 잠금으로 중복 게시 방지) |
| `workday.py` | 근무일 판단 |
| `holidays_override.txt` | 수동 근무일 지정 |

`.env`, `state/`, `logs/`, `venv/`는 git에 올리지 않는다.

## 주의

- 네이버 페이지 구조가 바뀌면 `naver_place.parse_feeds()`를 고쳐야 한다. 12:00 알림에 "소식 조회 실패"가 계속 뜨면 이것부터 확인한다.
- 요청은 식당당 하루 13번이다. 더 자주 돌리면 네이버에서 막힐 수 있다.

## 이력

- ~2026-10: `nlsomhansig` 인스타그램 계정을 Instaloader로 크롤링. 서버 IP·봇 계정이 Instagram에 막혀 중단.
- 2026-10: Mac 브라우저로 인스타 이미지를 찾아 서버로 넘기는 릴레이(`../nlsom-menu`)로 임시 대체.
- 2026-11: 식권 식당이 바뀌어 네이버 플레이스 소식 방식으로 전환, 레포 이름을 `nlsomhansig` → `lunch-menu-bot`으로 변경.
