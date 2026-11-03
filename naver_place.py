"""네이버 플레이스 '소식' 탭에서 글 목록을 가져온다.

공식 API가 없어서 pcmap.place.naver.com 페이지에 내장된 __APOLLO_STATE__ JSON을 읽는다.
로그인·쿠키가 필요 없다. 네이버가 페이지 구조를 바꾸면 parse_feeds()를 고쳐야 한다.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

FEED_URL = "https://pcmap.place.naver.com/restaurant/{place_id}/feed"
PLACE_URL = "https://map.naver.com/p/entry/place/{place_id}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)
TIMEOUT_SEC = 20
APOLLO_MARKER = "window.__APOLLO_STATE__"


@dataclass(frozen=True)
class FeedPost:
    feed_id: int
    title: str
    desc: str
    created: date
    image_url: str | None


def _get(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        return response.read()


def parse_feeds(html: str) -> list[FeedPost]:
    start = html.find(APOLLO_MARKER)
    if start < 0:
        raise ValueError("페이지에 __APOLLO_STATE__가 없음 (네이버 페이지 구조 변경 가능성)")
    brace = html.index("{", start)
    state, _ = json.JSONDecoder().raw_decode(html, brace)

    posts: dict[int, FeedPost] = {}
    for value in state.values():
        if not isinstance(value, dict) or value.get("__typename") != "Feed" or value.get("isDeleted"):
            continue
        feed_id = int(value["feedId"])
        media = value.get("media") or []
        image_url = next(
            (m.get("thumbnail") for m in media if m.get("mediaType") == "IMAGE" and m.get("thumbnail")),
            None,
        )
        # 고정글(isPinned)은 목록에 두 번 들어 있어 feedId로 중복을 없앤다
        posts[feed_id] = FeedPost(
            feed_id=feed_id,
            title=(value.get("title") or "").strip(),
            desc=(value.get("desc") or "").strip(),
            created=datetime.strptime(value["createdString"], "%Y%m%d").date(),
            image_url=image_url,
        )
    return sorted(posts.values(), key=lambda p: p.feed_id)


def fetch_feeds(place_id: str) -> list[FeedPost]:
    html = _get(FEED_URL.format(place_id=place_id)).decode("utf-8")
    return parse_feeds(html)


def download_image(url: str) -> bytes:
    return _get(url)
