from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from watermark_app.core.collage import COLLAGE_LAYOUTS, CollageLayout, CollageOptions


@dataclass
class CollageGroup:
    id: str
    name: str
    photo_paths: list[str]
    layout_name: str
    options: CollageOptions
    created_at: str
    updated_at: str
    jpg_quality: int = 95
    thumbnail_path: str = ""

    @classmethod
    def create(
        cls,
        name: str,
        photo_paths: list[Path],
        layout: CollageLayout,
        options: CollageOptions,
        jpg_quality: int = 95,
    ) -> "CollageGroup":
        now = timestamp()
        return cls(
            id=uuid4().hex,
            name=name,
            photo_paths=[str(path) for path in photo_paths],
            layout_name=layout.name,
            options=options,
            created_at=now,
            updated_at=now,
            jpg_quality=jpg_quality,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "CollageGroup":
        options_data = data.get("options") or {}
        return cls(
            id=str(data.get("id") or uuid4().hex),
            name=str(data.get("name") or "拼图组"),
            photo_paths=[str(path) for path in data.get("photo_paths") or []],
            layout_name=str(data.get("layout_name") or COLLAGE_LAYOUTS[0].name),
            options=CollageOptions(
                gap=int(options_data.get("gap", 8)),
                corner_radius=int(options_data.get("corner_radius", 0)),
                background_color=str(options_data.get("background_color", "#ffffff")),
                output_width=int(options_data.get("output_width", 2000)),
                output_height=int(options_data.get("output_height", 2000)),
            ),
            created_at=str(data.get("created_at") or timestamp()),
            updated_at=str(data.get("updated_at") or timestamp()),
            jpg_quality=int(data.get("jpg_quality", 95)),
            thumbnail_path=str(data.get("thumbnail_path") or ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "photo_paths": self.photo_paths,
            "layout_name": self.layout_name,
            "options": options_to_dict(self.options),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "jpg_quality": self.jpg_quality,
            "thumbnail_path": self.thumbnail_path,
        }

    def valid_paths(self, image_extensions: set[str]) -> list[Path]:
        return [
            Path(raw)
            for raw in self.photo_paths
            if Path(raw).is_file() and Path(raw).suffix.lower() in image_extensions
        ]

    def sanitized(self, image_extensions: set[str]) -> "CollageGroup | None":
        paths = self.valid_paths(image_extensions)
        if not paths:
            return None
        self.photo_paths = [str(path) for path in paths]
        return self

    def update_from_editor(
        self,
        photo_paths: list[Path],
        layout: CollageLayout,
        options: CollageOptions,
        jpg_quality: int = 95,
    ) -> None:
        self.photo_paths = [str(path) for path in photo_paths]
        self.layout_name = layout.name
        self.options = options
        self.jpg_quality = jpg_quality
        self.updated_at = timestamp()

    def copy(self, name: str) -> "CollageGroup":
        now = timestamp()
        return CollageGroup(
            id=uuid4().hex,
            name=name,
            photo_paths=list(self.photo_paths),
            layout_name=self.layout_name,
            options=CollageOptions(
                gap=self.options.gap,
                corner_radius=self.options.corner_radius,
                background_color=self.options.background_color,
                output_width=self.options.output_width,
                output_height=self.options.output_height,
            ),
            created_at=now,
            updated_at=now,
            jpg_quality=self.jpg_quality,
            thumbnail_path=self.thumbnail_path,
        )


@dataclass
class CollageGroupStore:
    groups: list[CollageGroup] = field(default_factory=list)

    @classmethod
    def from_json(cls, text: str, image_extensions: set[str]) -> "CollageGroupStore":
        if not text:
            return cls()
        try:
            raw_groups = json.loads(text)
        except json.JSONDecodeError:
            return cls()
        groups: list[CollageGroup] = []
        for item in raw_groups if isinstance(raw_groups, list) else []:
            if not isinstance(item, dict):
                continue
            group = CollageGroup.from_dict(item).sanitized(image_extensions)
            if group is not None:
                groups.append(group)
        return cls(groups)

    def to_json(self) -> str:
        return json.dumps([group.to_dict() for group in self.groups], ensure_ascii=False)

    def next_name(self) -> str:
        existing = {group.name for group in self.groups}
        index = 1
        while True:
            name = f"拼图组 {index}"
            if name not in existing:
                return name
            index += 1

    def by_id(self, group_id: str) -> CollageGroup | None:
        for group in self.groups:
            if group.id == group_id:
                return group
        return None

    def remove(self, group_id: str) -> None:
        self.groups = [group for group in self.groups if group.id != group_id]

    def duplicate_name(self, source_name: str) -> str:
        existing = {group.name for group in self.groups}
        base = f"{source_name} 副本"
        if base not in existing:
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"

    def reorder(self, group_ids: list[str]) -> None:
        by_id = {group.id: group for group in self.groups}
        reordered = [by_id[group_id] for group_id in group_ids if group_id in by_id]
        reordered.extend(group for group in self.groups if group.id not in group_ids)
        self.groups = reordered


def options_to_dict(options: CollageOptions) -> dict:
    return {
        "gap": int(options.gap),
        "corner_radius": int(options.corner_radius),
        "background_color": options.background_color,
        "output_width": int(options.output_width),
        "output_height": int(options.output_height),
    }


def layout_by_name(name: str) -> CollageLayout:
    for layout in COLLAGE_LAYOUTS:
        if layout.name == name:
            return layout
    return COLLAGE_LAYOUTS[0]


def safe_filename(name: str, used_names: set[str] | None = None, suffix: str = ".jpg") -> str:
    used_names = used_names if used_names is not None else set()
    base = re.sub(r'[\\/:*?"<>|]+', "_", name.strip()) or "collage"
    candidate = base
    index = 2
    while f"{candidate}{suffix}" in used_names:
        candidate = f"{base}_{index}"
        index += 1
    filename = f"{candidate}{suffix}"
    used_names.add(filename)
    return filename


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
