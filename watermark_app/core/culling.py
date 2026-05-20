from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


COLOR_LABELS = ["无", "红", "黄", "绿", "蓝"]


@dataclass
class PhotoPick:
    path: str
    rating: int = 0
    color_label: str = "无"
    status: str = "未定"

    @classmethod
    def from_dict(cls, data: dict) -> "PhotoPick":
        return cls(
            path=str(data.get("path") or ""),
            rating=max(0, min(5, int(data.get("rating", 0)))),
            color_label=str(data.get("color_label") or "无") if str(data.get("color_label") or "无") in COLOR_LABELS else "无",
            status=str(data.get("status") or "未定") if str(data.get("status") or "未定") in {"未定", "保留", "淘汰"} else "未定",
        )

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "rating": self.rating,
            "color_label": self.color_label,
            "status": self.status,
        }

    @property
    def display_name(self) -> str:
        path = Path(self.path)
        rating_text = "★" * self.rating if self.rating else "-"
        return f"{path.name}    {rating_text}    {self.status}    {self.color_label}"


class CullingStore:
    def __init__(self, picks: list[PhotoPick] | None = None) -> None:
        self.picks = picks or []

    @classmethod
    def from_json(cls, text: str, image_extensions: set[str]) -> "CullingStore":
        if not text:
            return cls()
        try:
            raw_items = json.loads(text)
        except json.JSONDecodeError:
            return cls()
        picks: list[PhotoPick] = []
        seen: set[str] = set()
        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict):
                continue
            pick = PhotoPick.from_dict(item)
            path = Path(pick.path)
            if not path.is_file() or path.suffix.lower() not in image_extensions or pick.path in seen:
                continue
            picks.append(pick)
            seen.add(pick.path)
        return cls(picks)

    def to_json(self) -> str:
        return json.dumps([pick.to_dict() for pick in self.picks], ensure_ascii=False)

    def add_paths(self, paths: list[str], image_extensions: set[str]) -> bool:
        existing = {pick.path for pick in self.picks}
        added = False
        for raw in paths:
            path = Path(raw)
            if not path.is_file() or path.suffix.lower() not in image_extensions or str(path) in existing:
                continue
            self.picks.append(PhotoPick(path=str(path)))
            existing.add(str(path))
            added = True
        return added

    def by_path(self, path: str | Path) -> PhotoPick | None:
        text = str(path)
        for pick in self.picks:
            if pick.path == text:
                return pick
        return None

    def remove_missing(self, image_extensions: set[str]) -> None:
        self.picks = [
            pick
            for pick in self.picks
            if Path(pick.path).is_file() and Path(pick.path).suffix.lower() in image_extensions
        ]

    def filtered(self, minimum_rating: int = 0, status: str = "全部") -> list[PhotoPick]:
        result = [pick for pick in self.picks if pick.rating >= minimum_rating]
        if status != "全部":
            result = [pick for pick in result if pick.status == status]
        return result

    def selected_for_delivery(self) -> list[PhotoPick]:
        return [pick for pick in self.picks if pick.status == "保留" or pick.rating >= 1]


def copy_picks_to_directory(picks: list[PhotoPick], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    used_names: set[str] = set()
    for pick in picks:
        source = Path(pick.path)
        if not source.is_file():
            continue
        target = directory / unique_name(source.name, used_names)
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def unique_name(name: str, used_names: set[str]) -> str:
    path = Path(name)
    stem = path.stem
    suffix = path.suffix
    candidate = name
    index = 2
    while candidate in used_names:
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    used_names.add(candidate)
    return candidate
