"""식권 식당들의 네이버 플레이스 '소식'에서 오늘 메뉴를 찾아 Slack #점심메뉴에 올린다.

    venv/bin/python main.py            # 평일 09:00~11:45 cron, 15분마다
    venv/bin/python main.py --final    # 12:00 마지막 확인. 메뉴를 못 찾은 식당이 있으면 알림 1회
    DRY_RUN=1 venv/bin/python main.py --date 2026-11-03   # Slack 없이 특정 날짜로 시험

이미 올린 소식은 feedId로 건너뛰고, 같은 날 새로 올라온 메뉴 소식은 계속 올린다.
첫 소식이 메뉴가 아닐 수 있고 하늘한정식뷔페는 11시 넘어 올릴 때도 있어서 12:00까지 매번 확인한다.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from naver_place import PLACE_URL, FeedPost, download_image, fetch_feeds
from slack_client import Slack, slack_escape
from state import day_state
from workday import workday_reason

BASE_DIR = Path(__file__).resolve().parent
KST = ZoneInfo("Asia/Seoul")

# (파일명용 slug, 표시 이름, 네이버 플레이스 ID)
RESTAURANTS = [
    ("haneul", "하늘한정식뷔페", "2089924926"),
    ("myeongin", "명인푸드한식뷔페", "2099805786"),
]

MENU_RE = re.compile(r"메뉴")
CLOSED_RE = re.compile(r"쉽니다|쉬어\s*갑니다|휴무|휴업|휴점|영업\s*(안|하지)")
MAX_IMAGE_SIDE = 2048

DRY_RUN = os.environ.get("DRY_RUN", "").strip() not in ("", "0", "false")
STATE_DIR = BASE_DIR / "state" / ("dry_run" if DRY_RUN else "")


def today_kst() -> date:
    return datetime.now(KST).date()


def log(message: str) -> None:
    print(f"{datetime.now(KST):%Y-%m-%d %H:%M:%S} {message}", flush=True)


def classify(post: FeedPost) -> str | None:
    if post.image_url and MENU_RE.search(post.title):
        return "menu"
    if CLOSED_RE.search(f"{post.title}\n{post.desc}"):
        return "closed"
    return None


def _save_image(data: bytes, dest: Path) -> None:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        image.convert("RGB").save(dest, "JPEG", quality=88)


def _post_menu(slack: Slack, day: date, slug: str, name: str, place_id: str, post: FeedPost) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / f"{day.isoformat()}_{slug}.jpg"
        _save_image(download_image(post.image_url), image_path)
        message = (
            f"📋 {day.month}월 {day.day}일 *{name}* 메뉴\n"
            f"{slack_escape(post.title)}\n"
            f"<{PLACE_URL.format(place_id=place_id)}|네이버 플레이스>"
        )
        slack.upload_image(image_path, f"{day.month}/{day.day} {name}", message)


def run(day: date, final: bool) -> int:
    workday, reason = workday_reason(day)
    if not workday:
        log(f"{day} 휴일({reason}), 확인 생략")
        return 0

    slack = Slack(DRY_RUN, log)
    errors: dict[str, str] = {}
    today_titles: dict[str, list[str]] = {}

    with day_state(STATE_DIR, day) as state:
        for slug, name, place_id in RESTAURANTS:
            try:
                posts = [p for p in fetch_feeds(place_id) if p.created == day]
            except Exception as exc:
                errors[name] = f"{type(exc).__name__}: {exc}"
                log(f"{name}: 소식 조회 실패 ({errors[name]})")
                continue
            today_titles[name] = [p.title for p in posts]

            for post in posts:
                if state.is_handled(place_id, post.feed_id):
                    continue
                kind = classify(post)
                if kind is None:
                    log(f"{name}: 메뉴가 아닌 소식이라 건너뜀 #{post.feed_id} {post.title!r}")
                    continue
                # 식당이 같은 글을 두 번 올리는 경우가 있다 (11/3 하늘한정식뷔페: 이미지 URL까지 동일)
                if kind == "menu" and state.has_image(place_id, post.image_url):
                    state.mark("skipped", place_id, post.feed_id)
                    log(f"{name}: 이미 올린 이미지와 같아 건너뜀 #{post.feed_id} {post.title!r}")
                    continue
                try:
                    if kind == "menu":
                        _post_menu(slack, day, slug, name, place_id, post)
                    else:
                        slack.post(f"🚫 {day.month}월 {day.day}일 *{name}*: {slack_escape(post.title)}")
                except Exception as exc:
                    log(f"{name}: Slack 전송 실패, 다음 확인 때 재시도 #{post.feed_id} ({type(exc).__name__}: {exc})")
                    continue
                state.mark(kind, place_id, post.feed_id, post.image_url)
                log(f"{name}: {'메뉴' if kind == 'menu' else '휴무'} 게시 #{post.feed_id} {post.title!r}")

        found = [name for _, name, place_id in RESTAURANTS if state.has_any(place_id)]
        log(f"{day} 확인 완료. 게시된 식당: {', '.join(found) or '없음'}")

        if final and not state.alerted:
            missing = [(name, place_id) for _, name, place_id in RESTAURANTS if not state.has_any(place_id)]
            if missing:
                lines = []
                for name, _ in missing:
                    if name in errors:
                        lines.append(f"• {name}: 소식 조회 실패 ({errors[name]})")
                    elif today_titles.get(name):
                        titles = ", ".join(f"'{t}'" for t in today_titles[name])
                        lines.append(f"• {name}: 오늘 소식은 있지만 메뉴로 판단되지 않음 ({slack_escape(titles)})")
                    else:
                        lines.append(f"• {name}: 오늘 올라온 소식 없음")
                slack.post("⚠️ 12:00까지 오늘 메뉴를 찾지 못한 식당이 있습니다\n" + "\n".join(lines))
                state.alerted = True
                log("미발견 알림 전송: " + ", ".join(name for name, _ in missing))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true", help="마지막 확인. 못 찾은 식당이 있으면 알림")
    parser.add_argument("--date", type=date.fromisoformat, help="시험용 날짜 (기본: 오늘, KST)")
    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")
    return run(args.date or today_kst(), args.final)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        log(f"예기치 못한 오류 ({type(exc).__name__}: {exc})")
        raise SystemExit(1)
