from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image


@dataclass
class RenamePlanItem:
    source: Path
    target: Path


def build_rename_plan(paths: list[Path], template: str, start_index: int = 1) -> list[RenamePlanItem]:
    used: set[str] = set()
    plan: list[RenamePlanItem] = []
    for offset, source in enumerate(paths):
        index = start_index + offset
        date_text = photo_date(source)
        raw_name = template.format(
            stem=source.stem,
            ext=source.suffix.lower().lstrip("."),
            index=f"{index:03d}",
            date=date_text,
        )
        safe = safe_stem(raw_name)
        candidate = f"{safe}{source.suffix.lower()}"
        unique = unique_filename(candidate, used)
        plan.append(RenamePlanItem(source=source, target=source.with_name(unique)))
    return plan


def apply_rename_plan(plan: list[RenamePlanItem]) -> None:
    for item in plan:
        if item.source == item.target:
            continue
        item.source.rename(item.target)


def photo_date(path: Path) -> str:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            value = exif.get(36867) or exif.get(306)
            if value:
                return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S").strftime("%Y%m%d")
    except Exception:
        pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")
    except OSError:
        return datetime.now().strftime("%Y%m%d")


def safe_stem(value: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
    text = re.sub(r"\s+", "_", text)
    return text or "photo"


def unique_filename(name: str, used: set[str]) -> str:
    path = Path(name)
    candidate = name
    index = 2
    while candidate in used:
        candidate = f"{path.stem}_{index}{path.suffix}"
        index += 1
    used.add(candidate)
    return candidate
