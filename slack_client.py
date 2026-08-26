from __future__ import annotations

import os
import time
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from instagram import TodayPost

MAX_RETRIES = 3
RETRY_DELAY_SEC = 10


def _get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} 환경변수가 설정되지 않았습니다.")
    return value


def _upload_with_retry(client: WebClient, channel_id: str, file_uploads: list, message: str, image_count: int) -> None:
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.files_upload_v2(
                channel=channel_id,
                file_uploads=file_uploads,
                initial_comment=message,
            )
        except SlackApiError as exc:
            error = exc.response.get("error", "unknown_error")
            last_exc = exc
            print(f"Slack 업로드 시도 {attempt}/{MAX_RETRIES} 실패 (SlackApiError: {error})", flush=True)
        except Exception as exc:
            last_exc = exc
            print(f"Slack 업로드 시도 {attempt}/{MAX_RETRIES} 실패 ({type(exc).__name__}: {exc})", flush=True)
        else:
            uploaded = response.get("files") or []
            if len(uploaded) != image_count:
                raise RuntimeError(
                    f"Slack 업로드 불일치: 요청 {image_count}장, 실제 업로드 {len(uploaded)}장"
                )
            print(f"Slack 업로드 확인: {len(uploaded)}장", flush=True)
            return

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY_SEC * attempt
            print(f"{delay}초 후 재시도...", flush=True)
            time.sleep(delay)

    raise RuntimeError(f"Slack 업로드 {MAX_RETRIES}회 모두 실패: {last_exc}") from last_exc


def upload_lunch_menu(posts: list[TodayPost], target_profile: str) -> None:
    if not posts:
        return

    token = _get_env("SLACK_BOT_TOKEN")
    channel_id = _get_env("SLACK_CHANNEL_ID")
    client = WebClient(token=token)

    image_paths: list[Path] = []
    for post in posts:
        image_paths.extend(post.image_paths)

    captions = [post.caption for post in posts if post.caption]
    caption_text = captions[0] if captions else "오늘의 점심 메뉴"
    image_count = len(image_paths)
    message = (
        f"오늘 점심 메뉴입니다! ({image_count}장)\n\n"
        f"{caption_text}\n\n"
        f"출처: @{target_profile}"
    )

    file_uploads = [
        {
            "file": str(path),
            "title": f"점심메뉴 {index + 1}",
        }
        for index, path in enumerate(image_paths)
    ]

    _upload_with_retry(client, channel_id, file_uploads, message, image_count)
