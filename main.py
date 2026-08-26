from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from instagram import fetch_today_posts
from slack_client import upload_lunch_menu
from state import load_state, save_state

KST = ZoneInfo("Asia/Seoul")


def main() -> int:
    load_dotenv()

    target_profile = os.environ.get("TARGET_PROFILE", "nlsomhansig").strip()
    today_str = datetime.now(KST).date().isoformat()

    state = load_state()
    state.reset_if_new_day(today_str)

    posts = fetch_today_posts(target_profile)
    if not posts:
        print(f"[{today_str}] 오늘 올라온 게시물이 없습니다.")
        return 0

    all_shortcodes = [post.shortcode for post in posts]
    unposted_codes = state.filter_unposted(all_shortcodes)
    if not unposted_codes:
        print(f"[{today_str}] 오늘 게시물을 이미 전송했습니다: {', '.join(all_shortcodes)}")
        return 0

    unposted = [post for post in posts if post.shortcode in unposted_codes]
    image_count = sum(len(post.image_paths) for post in unposted)

    upload_lunch_menu(unposted, target_profile)
    state.mark_posted(unposted_codes, today_str)
    save_state(state)

    print(
        f"[{today_str}] Slack 전송 완료: "
        f"게시물 {len(unposted)}건, 이미지 {image_count}장 "
        f"({', '.join(unposted_codes)})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"예기치 못한 오류 ({type(exc).__name__}): {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
