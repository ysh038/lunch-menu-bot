"""하루 단위 게시 기록. state/<YYYY-MM-DD>.json 에 식당별로 이미 올린 소식 feedId를 남긴다."""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class DayState:
    menu: dict[str, list[int]] = field(default_factory=dict)    # place_id → 올린 메뉴 소식
    closed: dict[str, list[int]] = field(default_factory=dict)  # place_id → 올린 휴무 소식
    images: dict[str, list[str]] = field(default_factory=dict)  # place_id → 올린 메뉴 이미지 URL
    skipped: dict[str, list[int]] = field(default_factory=dict) # place_id → 같은 이미지라 건너뛴 소식
    alerted: bool = False                                       # 12:00 미발견 알림 보냄

    def has_any(self, place_id: str) -> bool:
        return bool(self.menu.get(place_id) or self.closed.get(place_id))

    def is_handled(self, place_id: str, feed_id: int) -> bool:
        return any(feed_id in getattr(self, kind).get(place_id, []) for kind in ("menu", "closed", "skipped"))

    def has_image(self, place_id: str, image_url: str) -> bool:
        return image_url in self.images.get(place_id, [])

    def mark(self, kind: str, place_id: str, feed_id: int, image_url: str | None = None) -> None:
        getattr(self, kind).setdefault(place_id, []).append(feed_id)
        if kind == "menu" and image_url:
            self.images.setdefault(place_id, []).append(image_url)


@contextmanager
def day_state(state_dir: Path, day: date):
    """잠금을 잡은 채 그날 기록을 읽고, 블록이 끝나면 저장한다. cron이 겹쳐 돌아도 중복 게시를 막는다."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{day.isoformat()}.json"
    with (state_dir / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = DayState(**json.loads(path.read_text(encoding="utf-8"))) if path.exists() else DayState()
        try:
            yield state
        finally:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(path)
