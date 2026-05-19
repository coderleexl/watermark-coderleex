from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QListWidgetItem, QTreeWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel as QLabel,
    CaptionLabel,
    ListWidget as QListWidget,
    PushButton as QPushButton,
    TreeWidget as QTreeWidget,
)


COMMON_RATIOS = [
    (1, 1),
    (3, 2),
    (2, 3),
    (4, 3),
    (3, 4),
    (16, 9),
    (9, 16),
    (5, 4),
    (4, 5),
]


class CollagePhotoSelector(QWidget):
    collage_order_changed = Signal(list)

    def __init__(self, image_extensions: set[str]) -> None:
        super().__init__()
        self.image_extensions = image_extensions
        self.photo_paths: list[Path] = []
        self.ratio_groups: dict[str, QTreeWidgetItem] = {}
        self._syncing = False

        self.available_tree = QTreeWidget()
        self.available_tree.setHeaderHidden(True)
        self.available_tree.setRootIsDecorated(True)
        self.available_tree.setUniformRowHeights(True)
        self.available_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.available_tree.itemChanged.connect(self.on_available_item_changed)
        self.available_tree.currentItemChanged.connect(self.on_available_item_selected)

        self.available_preview = QLabel("点击照片预览")
        self.available_preview.setObjectName("previewLabel")
        self.available_preview.setAlignment(Qt.AlignCenter)
        self.available_preview.setMinimumHeight(150)

        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.selected_list.setDefaultDropAction(Qt.MoveAction)
        self.selected_list.model().rowsMoved.connect(lambda *_: self.emit_order_changed())

        self.add_selected_button = QPushButton("加入拼图")
        self.add_selected_button.clicked.connect(self.add_highlighted)
        self.add_all_button = QPushButton("全部加入")
        self.add_all_button.clicked.connect(self.add_all)
        self.remove_selected_button = QPushButton("移除选中")
        self.remove_selected_button.clicked.connect(self.remove_highlighted)
        self.clear_selected_button = QPushButton("清空已选")
        self.clear_selected_button.clicked.connect(self.clear_selected)

        self.available_hint = CaptionLabel("可选照片：0 张，按比例分类，点击预览，勾选加入拼图")
        self.available_hint.setObjectName("mutedLabel")
        self.selected_hint = CaptionLabel("已选照片：0 张，拖拽调整拼图顺序")
        self.selected_hint.setObjectName("mutedLabel")

        available_buttons = QHBoxLayout()
        available_buttons.setSpacing(6)
        available_buttons.addWidget(self.add_selected_button)
        available_buttons.addWidget(self.add_all_button)

        selected_buttons = QHBoxLayout()
        selected_buttons.setSpacing(6)
        selected_buttons.addWidget(self.remove_selected_button)
        selected_buttons.addWidget(self.clear_selected_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.available_hint)
        layout.addWidget(self.available_preview, 1)
        layout.addWidget(self.available_tree, 2)
        layout.addLayout(available_buttons)
        layout.addWidget(self.selected_hint)
        layout.addWidget(self.selected_list, 2)
        layout.addLayout(selected_buttons)

    def add_files(self, files: list[str]) -> None:
        added = False
        first_added: QTreeWidgetItem | None = None
        for raw in files:
            path = Path(raw)
            if not path.is_file() or path.suffix.lower() not in self.image_extensions or path in self.photo_paths:
                continue
            self.photo_paths.append(path)
            ratio_key, ratio_label = self.photo_ratio(path)
            group = self.ratio_groups.get(ratio_key)
            if group is None:
                group = QTreeWidgetItem([ratio_label])
                group.setData(0, Qt.UserRole, "")
                group.setData(0, Qt.UserRole + 1, ratio_key)
                self.available_tree.addTopLevelItem(group)
                self.ratio_groups[ratio_key] = group
            item = QTreeWidgetItem([path.name])
            item.setData(0, Qt.UserRole, str(path))
            item.setData(0, Qt.UserRole + 1, ratio_key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            item.setToolTip(0, str(path))
            group.addChild(item)
            group.setText(0, f"{ratio_label} ({group.childCount()})")
            group.setExpanded(True)
            first_added = first_added or item
            added = True
        if first_added is not None and self.current_available_path() is None:
            self.available_tree.setCurrentItem(first_added)
        if added:
            self.emit_order_changed()

    def clear(self) -> None:
        self.photo_paths.clear()
        self.ratio_groups.clear()
        self.available_tree.clear()
        self.selected_list.clear()
        self.available_preview.clear()
        self.available_preview.setText("点击照片预览")
        self.emit_order_changed()

    def selected_photos(self) -> list[Path]:
        paths: list[Path] = []
        for index in range(self.selected_list.count()):
            raw = self.selected_list.item(index).data(Qt.UserRole)
            if raw:
                paths.append(Path(str(raw)))
        return paths

    def all_photos(self) -> list[Path]:
        return list(self.photo_paths)

    def set_selected_photos(self, paths: list[Path]) -> None:
        self.clear_selected()
        missing = [path for path in paths if path not in self.photo_paths]
        if missing:
            self.add_files([str(path) for path in missing])
        self.add_selected_paths(paths)

    def add_highlighted(self) -> None:
        paths = [path for path in self.highlighted_available_paths() if path is not None]
        self.add_selected_paths(paths)

    def add_all(self) -> None:
        self.add_selected_paths(self.photo_paths)

    def add_selected_paths(self, paths: list[Path]) -> None:
        existing = set(self.selected_photos())
        for path in paths:
            if path in existing:
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.selected_list.addItem(item)
            existing.add(path)
            self.set_available_checked(path, True)
        self.emit_order_changed()

    def remove_highlighted(self) -> None:
        rows = sorted((self.selected_list.row(item) for item in self.selected_list.selectedItems()), reverse=True)
        for row in rows:
            item = self.selected_list.takeItem(row)
            raw = item.data(Qt.UserRole)
            if raw:
                self.set_available_checked(Path(str(raw)), False)
        self.emit_order_changed()

    def clear_selected(self) -> None:
        self.selected_list.clear()
        self._syncing = True
        for item in self.available_photo_items():
            item.setCheckState(0, Qt.Unchecked)
        self._syncing = False
        self.emit_order_changed()

    def on_available_item_changed(self, item: QTreeWidgetItem) -> None:
        if self._syncing:
            return
        raw = item.data(0, Qt.UserRole)
        if not raw:
            return
        path = Path(str(raw))
        if item.checkState(0) == Qt.Checked:
            self.add_selected_paths([path])
        else:
            self.remove_selected_path(path)

    def on_available_item_selected(self, current: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        raw = current.data(0, Qt.UserRole)
        if not raw:
            if current.childCount() > 0:
                self.available_tree.setCurrentItem(current.child(0))
            return
        self.update_available_preview(Path(str(raw)))

    def remove_selected_path(self, path: Path) -> None:
        for index in range(self.selected_list.count() - 1, -1, -1):
            item = self.selected_list.item(index)
            if Path(str(item.data(Qt.UserRole))) == path:
                self.selected_list.takeItem(index)
        self.emit_order_changed()

    def set_available_checked(self, path: Path, checked: bool) -> None:
        self._syncing = True
        for item in self.available_photo_items():
            raw = item.data(0, Qt.UserRole)
            if raw and Path(str(raw)) == path:
                item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                break
        self._syncing = False

    def current_available_path(self) -> Path | None:
        item = self.available_tree.currentItem()
        if item is None:
            return None
        raw = item.data(0, Qt.UserRole)
        return Path(str(raw)) if raw else None

    def highlighted_available_paths(self) -> list[Path]:
        paths: list[Path] = []
        for item in self.available_tree.selectedItems():
            raw = item.data(0, Qt.UserRole)
            if raw:
                paths.append(Path(str(raw)))
        return paths

    def available_photo_items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        for group_index in range(self.available_tree.topLevelItemCount()):
            group = self.available_tree.topLevelItem(group_index)
            for child_index in range(group.childCount()):
                items.append(group.child(child_index))
        return items

    def update_available_preview(self, path: Path) -> None:
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail((320, 180), Image.Resampling.LANCZOS)
            pixmap = QPixmap.fromImage(ImageQt(image))
            self.available_preview.setPixmap(pixmap)
        except Exception as exc:
            self.available_preview.setText(f"预览失败: {exc}")

    def photo_ratio(self, path: Path) -> tuple[str, str]:
        try:
            with Image.open(path) as image:
                width, height = ImageOps.exif_transpose(image).size
        except Exception:
            width, height = 1, 1
        ratio_w, ratio_h = self.normalized_ratio(width, height)
        orientation = "正方形" if ratio_w == ratio_h else ("横图" if width >= height else "竖图")
        return f"{ratio_w}x{ratio_h}", f"{orientation} {ratio_w}:{ratio_h}"

    def normalized_ratio(self, width: int, height: int) -> tuple[int, int]:
        ratio = width / max(1, height)
        for ratio_w, ratio_h in COMMON_RATIOS:
            if abs(ratio - ratio_w / ratio_h) <= 0.015:
                return ratio_w, ratio_h
        divisor = self.greatest_common_divisor(max(1, width), max(1, height))
        ratio_w = max(1, width // divisor)
        ratio_h = max(1, height // divisor)
        while ratio_w > 99 or ratio_h > 99:
            ratio_w = max(1, round(ratio_w / 2))
            ratio_h = max(1, round(ratio_h / 2))
        return ratio_w, ratio_h

    def greatest_common_divisor(self, a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return max(1, a)

    def emit_order_changed(self) -> None:
        self.update_counts()
        self.collage_order_changed.emit(self.selected_photos())

    def update_counts(self) -> None:
        self.available_hint.setText(f"可选照片：{len(self.photo_paths)} 张，按比例分类，点击预览，勾选加入拼图")
        self.selected_hint.setText(f"已选照片：{self.selected_list.count()} 张，拖拽调整拼图顺序")
