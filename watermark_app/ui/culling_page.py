from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QListWidgetItem, QMessageBox, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel as QLabel,
    CaptionLabel,
    ComboBox as QComboBox,
    ListWidget as QListWidget,
    PrimaryPushButton,
    PushButton as QPushButton,
    SpinBox as QSpinBox,
)

from watermark_app.core.culling import COLOR_LABELS, CullingStore, PhotoPick, copy_picks_to_directory
from watermark_app.core.i18n import tr


class PhotoCullingPage(QWidget):
    changed = Signal()

    def __init__(self, settings: QSettings, image_extensions: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cullingPage")
        self.settings = settings
        self.image_extensions = image_extensions
        self.store = CullingStore()
        self._restoring = False
        self.current_info_base = "选片: -"

        self.import_button = QPushButton()
        self.import_button.clicked.connect(self.choose_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self.clear_photos)
        self.copy_button = PrimaryPushButton()
        self.copy_button.clicked.connect(self.copy_selected)

        self.photo_list = QListWidget()
        self.photo_list.currentItemChanged.connect(self.on_photo_selected)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.info_label = CaptionLabel()
        self.info_label.setObjectName("mutedLabel")

        self.rating_spin = QSpinBox()
        self.rating_spin.setRange(0, 5)
        self.rating_spin.valueChanged.connect(lambda *_: self.update_current_pick())
        self.color_combo = QComboBox()
        for label in COLOR_LABELS:
            self.color_combo.addItem(label, userData=label)
        self.color_combo.currentIndexChanged.connect(lambda *_: self.update_current_pick())
        self.status_combo = QComboBox()
        for label in ["未定", "保留", "淘汰"]:
            self.status_combo.addItem(label, userData=label)
        self.status_combo.currentIndexChanged.connect(lambda *_: self.update_current_pick())

        self.filter_rating_spin = QSpinBox()
        self.filter_rating_spin.setRange(0, 5)
        self.filter_rating_spin.valueChanged.connect(lambda *_: self.refresh_list())
        self.filter_status_combo = QComboBox()
        for label in ["全部", "未定", "保留", "淘汰"]:
            self.filter_status_combo.addItem(label, userData=label)
        self.filter_status_combo.currentIndexChanged.connect(lambda *_: self.refresh_list())

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(16, 8, 16, 16)
        page_layout.setSpacing(10)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        import_row = QHBoxLayout()
        import_row.setSpacing(6)
        import_row.addWidget(self.import_button)
        import_row.addWidget(self.clear_button)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.min_rating_label = CaptionLabel()
        filter_row.addWidget(self.min_rating_label)
        filter_row.addWidget(self.filter_rating_spin)
        filter_row.addWidget(self.filter_status_combo)
        left_layout.addLayout(import_row)
        left_layout.addLayout(filter_row)
        left_layout.addWidget(self.photo_list, 1)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        center_layout.addWidget(self.preview_label, 1)
        center_layout.addWidget(self.info_label)

        controls = QWidget()
        controls.setObjectName("settingsPanel")
        controls.setMinimumWidth(320)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        self.rating_label = CaptionLabel()
        self.color_label = CaptionLabel()
        self.status_label = CaptionLabel()
        controls_layout.addWidget(self.rating_label)
        controls_layout.addWidget(self.rating_spin)
        controls_layout.addWidget(self.color_label)
        controls_layout.addWidget(self.color_combo)
        controls_layout.addWidget(self.status_label)
        controls_layout.addWidget(self.status_combo)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.copy_button)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(controls)
        splitter.setSizes([320, 860, 320])
        splitter.setHandleWidth(3)
        page_layout.addWidget(splitter, 1)

        self.refresh_texts()
        self.restore()

    def refresh_texts(self) -> None:
        self.import_button.setText(tr("common.import_photos"))
        self.clear_button.setText(tr("common.clear"))
        self.copy_button.setText(tr("culling.copy_selected"))
        self.min_rating_label.setText(tr("culling.min_rating"))
        self.rating_label.setText(tr("culling.rating"))
        self.color_label.setText(tr("culling.color"))
        self.status_label.setText(tr("culling.status"))
        if not self.current_path():
            self.preview_label.setText(tr("culling.empty"))
            self.info_label.setText(f"{tr('app.culling')}: -")
            self.current_info_base = self.info_label.text()

    def choose_files(self) -> None:
        dialog = QFileDialog(self, "选择选片照片", str(Path.home()))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilter("图片 (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
        if dialog.exec():
            if self.store.add_paths(dialog.selectedFiles(), self.image_extensions):
                self.save()
                self.refresh_list(select_first=True)

    def clear_photos(self) -> None:
        self.store = CullingStore()
        self.settings.remove("culling_store_json")
        self.photo_list.clear()
        self.preview_label.clear()
        self.preview_label.setText(tr("culling.empty"))
        self.info_label.setText(f"{tr('app.culling')}: -")
        self.current_info_base = self.info_label.text()

    def restore(self) -> None:
        self.store = CullingStore.from_json(str(self.settings.value("culling_store_json", "")), self.image_extensions)
        self.save()
        self.refresh_list(select_first=True)

    def save(self) -> None:
        self.settings.setValue("culling_store_json", self.store.to_json())

    def refresh_list(self, select_first: bool = False) -> None:
        current_path = self.current_path()
        self.photo_list.blockSignals(True)
        self.photo_list.clear()
        picks = self.store.filtered(self.filter_rating_spin.value(), self.filter_status_combo.currentData() or "全部")
        for pick in picks:
            item = QListWidgetItem(pick.display_name)
            item.setData(Qt.UserRole, pick.path)
            item.setToolTip(pick.path)
            self.photo_list.addItem(item)
            if pick.path == current_path:
                self.photo_list.setCurrentItem(item)
        if select_first and self.photo_list.count() > 0 and self.photo_list.currentItem() is None:
            self.photo_list.setCurrentRow(0)
        self.photo_list.blockSignals(False)
        if self.photo_list.currentItem() is not None:
            self.on_photo_selected(self.photo_list.currentItem())
        self.update_summary()

    def current_path(self) -> str:
        item = self.photo_list.currentItem()
        return str(item.data(Qt.UserRole)) if item is not None and item.data(Qt.UserRole) else ""

    def current_pick(self) -> PhotoPick | None:
        path = self.current_path()
        return self.store.by_path(path) if path else None

    def on_photo_selected(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        pick = self.store.by_path(str(current.data(Qt.UserRole)))
        if pick is None:
            return
        self._restoring = True
        self.rating_spin.setValue(pick.rating)
        self.set_combo_value(self.color_combo, pick.color_label)
        self.set_combo_value(self.status_combo, pick.status)
        self._restoring = False
        self.update_preview(Path(pick.path))

    def update_current_pick(self) -> None:
        if self._restoring:
            return
        pick = self.current_pick()
        if pick is None:
            return
        pick.rating = self.rating_spin.value()
        pick.color_label = self.color_combo.currentData() or "无"
        pick.status = self.status_combo.currentData() or "未定"
        self.save()
        self.refresh_current_item()
        self.update_summary()

    def refresh_current_item(self) -> None:
        item = self.photo_list.currentItem()
        pick = self.current_pick()
        if item is not None and pick is not None:
            item.setText(pick.display_name)

    def update_preview(self, path: Path) -> None:
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGBA")
            original = image.size
            image.thumbnail((self.preview_label.width() - 24, self.preview_label.height() - 24), Image.Resampling.LANCZOS)
            self.preview_label.setPixmap(QPixmap.fromImage(ImageQt(image)))
            self.info_label.setText(f"{tr('app.culling')}: {path.name}    原图: {original[0]} x {original[1]}")
            self.current_info_base = self.info_label.text()
            self.update_summary()
        except Exception as exc:
            self.preview_label.setText(f"预览失败: {exc}")

    def update_summary(self) -> None:
        total = len(self.store.picks)
        keep = len([pick for pick in self.store.picks if pick.status == "保留"])
        reject = len([pick for pick in self.store.picks if pick.status == "淘汰"])
        selected = len(self.store.selected_for_delivery())
        if total:
            self.info_label.setText(f"{self.current_info_base}    总数 {total} / 保留 {keep} / 淘汰 {reject} / 精选 {selected}")

    def copy_selected(self) -> None:
        picks = self.store.selected_for_delivery()
        if not picks:
            QMessageBox.information(self, tr("culling.no_picks"), tr("culling.set_rating_or_keep"))
            return
        dialog = QFileDialog(self, "选择精选照片复制目录", str(Path.home()))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if not dialog.exec():
            return
        selected = dialog.selectedFiles()
        if not selected:
            return
        copied = copy_picks_to_directory(picks, Path(selected[0]))
        QMessageBox.information(self, tr("culling.copy_done"), tr("culling.copied_count", count=len(copied)))

    def set_combo_value(self, widget: QComboBox, value: str) -> None:
        for index in range(widget.count()):
            if widget.itemData(index) == value or widget.itemText(index) == value:
                widget.setCurrentIndex(index)
                return
