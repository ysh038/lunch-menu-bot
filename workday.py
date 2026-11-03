"""근무일 판단. 우선순위: holidays_override.txt > 주말 > 한국 공휴일(대체공휴일 포함).

    venv/bin/python workday.py [YYYY-MM-DD]   # 근무일이면 종료 코드 0, 휴일이면 1
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import holidays

OVERRIDE_FILE = Path(__file__).resolve().parent / "holidays_override.txt"


def load_overrides(path: Path = OVERRIDE_FILE) -> dict[date, str]:
    overrides: dict[date, str] = {}
    if not path.exists():
        return overrides
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or parts[1] not in ("on", "off"):
            raise ValueError(f"{path.name} {lineno}번째 줄 형식 오류: {raw!r}")
        overrides[date.fromisoformat(parts[0])] = parts[1]
    return overrides


def workday_reason(day: date) -> tuple[bool, str]:
    overrides = load_overrides()
    if day in overrides:
        return overrides[day] == "on", f"수동 지정({overrides[day]})"
    if day.weekday() >= 5:
        return False, "주말"
    name = holidays.KR(years=day.year, language="ko").get(day)
    if name:
        return False, f"공휴일({name})"
    return True, "평일"


if __name__ == "__main__":
    from main import today_kst

    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else today_kst()
    ok, reason = workday_reason(target)
    print(f"{target} {'근무일' if ok else '휴일'}: {reason}")
    raise SystemExit(0 if ok else 1)
