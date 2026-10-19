from __future__ import annotations

import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import instaloader
import requests
from instaloader.exceptions import AbortDownloadException, InstaloaderException

import instaloader_patch

instaloader_patch.apply()

KST = ZoneInfo("Asia/Seoul")
DOWNLOAD_DIR = Path("downloads")
MAX_POSTS_TO_CHECK = 20
MAX_POSTS_PER_DAY = 10
FETCH_TIMEOUT_SEC = 60

# 인스타 웹 프로필 화면이 게시물 그리드를 불러올 때 쓰는 REST 경로.
# GraphQL 게시물 쿼리가 feedback_required로 막혀도 이 경로는 동작한다.
FEED_API_URL = "https://www.instagram.com/api/v1/feed/user/{username}/username/"
FEED_API_COUNT = 12
WEB_APP_ID = "936619743392459"
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_CAROUSEL = 8


@dataclass
class TodayPost:
    image_paths: list[Path]
    shortcode: str
    caption: str


@dataclass
class _FeedNode:
    is_video: bool
    display_url: str


class _FeedPost:
    """웹 REST 피드 item을 instaloader.Post와 같은 속성으로 다루기 위한 어댑터."""

    def __init__(self, item: dict) -> None:
        self._item = item
        self.shortcode: str = item["code"]
        # instaloader.Post.date_utc와 동일하게 naive UTC datetime
        self.date_utc = datetime.fromtimestamp(item["taken_at"], timezone.utc).replace(tzinfo=None)
        self.typename = "GraphSidecar" if item.get("media_type") == MEDIA_TYPE_CAROUSEL else "GraphImage"
        self.caption: str | None = (item.get("caption") or {}).get("text")
        self.url = _best_image_url(item)

    def get_sidecar_nodes(self) -> list[_FeedNode]:
        return [
            _FeedNode(
                is_video=media.get("media_type") == MEDIA_TYPE_VIDEO,
                display_url=_best_image_url(media),
            )
            for media in self._item.get("carousel_media") or []
        ]


def _best_image_url(media: dict) -> str:
    # candidates는 해상도 내림차순
    return media["image_versions2"]["candidates"][0]["url"]


def _create_loader() -> instaloader.Instaloader:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    return instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=str(DOWNLOAD_DIR / "{target}"),
    )


def _load_session(loader: instaloader.Instaloader) -> None:
    username = os.environ.get("INSTAGRAM_USERNAME", "").strip()
    if not username:
        raise ValueError("INSTAGRAM_USERNAME 환경변수가 설정되지 않았습니다.")

    session_path = Path("session")
    if not session_path.exists():
        raise FileNotFoundError(
            "session 파일이 없습니다. README의 안내에 따라 instaloader --login으로 생성하세요."
        )

    loader.load_session_from_file(username, filename=str(session_path))


def _fetch_feed_posts(loader: instaloader.Instaloader, target_profile: str) -> list[_FeedPost]:
    session = loader.context._session
    response = session.get(
        FEED_API_URL.format(username=target_profile),
        params={"count": FEED_API_COUNT},
        headers={
            "X-IG-App-ID": WEB_APP_ID,
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": session.cookies.get("csrftoken", ""),
            "Referer": f"https://www.instagram.com/{target_profile}/",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok":
        raise ValueError(f"status={data.get('status')} message={data.get('message')}")
    return [_FeedPost(item) for item in data.get("items", [])]


def _iter_posts(loader: instaloader.Instaloader, target_profile: str):
    try:
        return _fetch_feed_posts(loader, target_profile)
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"  ! 웹 피드 API 실패 ({type(exc).__name__}: {exc}), GraphQL로 재시도")
        profile = instaloader.Profile.from_username(loader.context, target_profile)
        return profile.get_posts()


def _post_date_kst(post: instaloader.Post | _FeedPost) -> datetime.date:
    # date_utc는 naive datetime(tzinfo 없음)이므로 UTC를 명시한 뒤 KST 변환
    return post.date_utc.replace(tzinfo=timezone.utc).astimezone(KST).date()


def _download_post_images(post: instaloader.Post | _FeedPost, target_profile: str) -> list[Path]:
    profile_dir = DOWNLOAD_DIR / target_profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    if post.typename == "GraphSidecar":
        image_index = 0
        for node in post.get_sidecar_nodes():
            if node.is_video:
                continue
            dest = profile_dir / f"{post.shortcode}_{image_index}.jpg"
            urllib.request.urlretrieve(node.display_url, dest)
            paths.append(dest)
            image_index += 1
        return paths

    dest = profile_dir / f"{post.shortcode}.jpg"
    urllib.request.urlretrieve(post.url, dest)
    return [dest]


def _fetch_today_posts_inner(target_profile: str) -> list[TodayPost]:
    today = datetime.now(KST).date()
    today_posts: list[TodayPost] = []

    loader = _create_loader()
    _load_session(loader)

    print(f"@{target_profile} 오늘({today}) 게시물 확인 중...")

    for index, post in enumerate(_iter_posts(loader, target_profile)):
        if index >= MAX_POSTS_TO_CHECK:
            break

        post_date = _post_date_kst(post)
        print(f"  - {post.shortcode} ({post_date})")

        if post_date < today:
            break

        if post_date == today:
            image_paths = _download_post_images(post, target_profile)
            if not image_paths:
                print(f"  ! {post.shortcode}: 이미지 없음 (동영상 전용 게시물일 수 있음), 건너뜀")
                continue
            caption = post.caption or "오늘의 점심 메뉴"
            today_posts.append(
                TodayPost(
                    image_paths=image_paths,
                    shortcode=post.shortcode,
                    caption=caption,
                )
            )

            if len(today_posts) >= MAX_POSTS_PER_DAY:
                print(f"오늘 게시물 {MAX_POSTS_PER_DAY}개 도달, 조회 중단.")
                break

    today_posts.reverse()
    if today_posts:
        total_images = sum(len(post.image_paths) for post in today_posts)
        print(
            f"오늘 게시물 {len(today_posts)}건, 이미지 {total_images}장 발견 "
            f"({', '.join(post.shortcode for post in today_posts)})"
        )

    return today_posts


def fetch_today_posts(target_profile: str | None = None) -> list[TodayPost]:
    profile_name = (target_profile or os.environ.get("TARGET_PROFILE", "nlsomhansig")).strip()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_fetch_today_posts_inner, profile_name)
        try:
            return future.result(timeout=FETCH_TIMEOUT_SEC)
        except FuturesTimeout as exc:
            raise RuntimeError(
                f"Instagram 조회 시간 초과 ({FETCH_TIMEOUT_SEC}초). "
                "잠시 후 다시 시도하세요."
            ) from exc
        except (InstaloaderException, AbortDownloadException) as exc:
            raise RuntimeError(f"Instagram 조회 실패: {exc}") from exc
