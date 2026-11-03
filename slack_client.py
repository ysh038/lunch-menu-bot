from __future__ import annotations

import os
from pathlib import Path

from slack_sdk import WebClient


def slack_escape(text: str) -> str:
    # 식당이 쓴 글이 <!channel> 같은 멘션이나 링크로 해석되지 않게 한다
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Slack:
    def __init__(self, dry_run: bool, log) -> None:
        self._dry_run = dry_run
        self._log = log
        if dry_run:
            self._client = None
            self._channel = ""
            return
        token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
        channel = os.environ.get("SLACK_CHANNEL_ID", "").strip()
        if not token or not channel:
            raise ValueError(".env에 SLACK_BOT_TOKEN, SLACK_CHANNEL_ID가 필요합니다.")
        self._client = WebClient(token=token)
        self._channel = channel

    def upload_image(self, image_path: Path, title: str, message: str) -> None:
        if self._dry_run:
            self._log(f"[DRY_RUN] Slack 업로드 생략: {image_path.name} / {message!r}")
            return
        # files_upload_v2 = files.getUploadURLExternal → 업로드 → files.completeUploadExternal
        response = self._client.files_upload_v2(
            channel=self._channel,
            file=str(image_path),
            filename=image_path.name,
            title=title,
            initial_comment=message,
        )
        if len(response.get("files") or []) != 1:
            raise RuntimeError("Slack 업로드 응답에 파일이 없음")

    def post(self, text: str) -> None:
        if self._dry_run:
            self._log(f"[DRY_RUN] Slack 메시지 생략: {text!r}")
            return
        self._client.chat_postMessage(channel=self._channel, text=text, unfurl_links=False)
