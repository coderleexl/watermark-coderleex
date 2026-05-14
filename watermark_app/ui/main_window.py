from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from watermark_app.core.exif import PhotoMetadata, read_photo_metadata
from watermark_app.core.renderer import render_image, save_rendered, TITLE_FONTS
from watermark_app.core.templates import RenderOptions, TemplateKind, WatermarkPosition


WATERMARK_DIR = Path("/Users/lixinglin/Documents/水印")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
PREVIEW_MAX_SOURCE_EDGE = 1400


class DropListWidget(QListWidget):
    def __init__(self, on_files_dropped):
        super().__init__()
        self.on_files_dropped = on_files_dropped
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SingleSelection)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        self.on_files_dropped(paths)
        event.acceptProposedAction()


class ResettableSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation, default_value: int) -> None:
        super().__init__(orientation)
        self.default_value = default_value

    def mouseDoubleClickEvent(self, event) -> None:
        self.setValue(self.default_value)
        event.accept()

    def wheelEvent(self, event) -> None:
        # Only accept wheel events when the slider has explicit focus
        # (i.e. the user clicked on it). This prevents accidental value
        # changes when scrolling through a parent QScrollArea.
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)


class QuietDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NumericSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        value: float,
        *,
        decimals: int = 1,
        step: float = 0.1,
        suffix: str = "",
    ) -> None:
        super().__init__()
        self.decimals = decimals
        self.factor = 10**decimals
        self.default_value = float(value)
        self.slider = ResettableSlider(Qt.Horizontal, self._to_slider(value))
        self.slider.setRange(self._to_slider(minimum), self._to_slider(maximum))
        self.slider.setSingleStep(max(1, self._to_slider(step)))
        self.slider.setPageStep(max(1, self._to_slider(step * 10)))
        self.slider.setTracking(True)
        self.slider.setToolTip("双击恢复默认值")

        self.input = QuietDoubleSpinBox()
        self.input.setRange(minimum, maximum)
        self.input.setDecimals(decimals)
        self.input.setSingleStep(step)
        self.input.setSuffix(suffix)
        self.input.setKeyboardTracking(False)
        self.input.setFixedWidth(82 if suffix else 74)
        self.input.setValue(value)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.input)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.input.valueChanged.connect(self._on_input_changed)

    def value(self) -> float:
        return self.input.value()

    def setValue(self, value: float) -> None:
        value = max(self.input.minimum(), min(self.input.maximum(), float(value)))
        self.input.setValue(value)
        self.slider.setValue(self._to_slider(value))

    def _to_slider(self, value: float) -> int:
        return int(round(float(value) * self.factor))

    def _from_slider(self, value: int) -> float:
        return value / self.factor

    def _on_slider_changed(self, value: int) -> None:
        numeric_value = self._from_slider(value)
        if abs(self.input.value() - numeric_value) > 1 / self.factor / 2:
            self.input.blockSignals(True)
            self.input.setValue(numeric_value)
            self.input.blockSignals(False)
        self.valueChanged.emit(numeric_value)

    def _on_input_changed(self, value: float) -> None:
        slider_value = self._to_slider(value)
        if self.slider.value() != slider_value:
            self.slider.blockSignals(True)
            self.slider.setValue(slider_value)
            self.slider.blockSignals(False)
        self.valueChanged.emit(value)


class CollapsibleSection(QWidget):
    def __init__(self, title: str, checked: bool | None = None) -> None:
        super().__init__()
        self.title = title
        self.header = QToolButton()
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setText(title)
        self.header.setArrowType(Qt.DownArrow)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setAutoRaise(True)
        self.header.setStyleSheet(
            """
            QToolButton {
                border: 0;
                padding: 7px 4px;
                font-weight: 600;
                text-align: left;
            }
            QToolButton:hover {
                background: rgba(127, 127, 127, 0.10);
            }
            """
        )
        self.header.clicked.connect(self.on_header_clicked)
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(self.header, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        layout.addLayout(header_row)
        layout.addWidget(self.body)
        self.enable_checkbox: QCheckBox | None = None
        if checked is not None:
            self.enable_checkbox = QCheckBox("启用")
            self.enable_checkbox.setChecked(checked)
            header_row.addWidget(self.enable_checkbox)

    def on_header_clicked(self) -> None:
        expanded = self.header.isChecked()
        self.body.setVisible(expanded)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def is_enabled(self) -> bool:
        return True if self.enable_checkbox is None else self.enable_checkbox.isChecked()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coderleex Watermark")
        self.resize(1320, 860)

        self.photo_paths: list[Path] = []
        self.current_metadata = PhotoMetadata()
        self.settings = QSettings("coderleex", "watermark")
        self._restoring_settings = False
        self.watermark_dir = Path(self.settings.value("watermark_dir", str(WATERMARK_DIR)))
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_preview)

        self.photo_list = DropListWidget(self.add_files)
        self.photo_list.currentItemChanged.connect(self.on_photo_changed)
        self.photo_count_label = QLabel("已选择 0 张照片")

        self.preview_label = QLabel("拖入照片或点击导入")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("background:#202020;color:#cfcfcf;")

        self.meta_label = QLabel("EXIF: -")
        self.meta_label.setWordWrap(True)
        self.preview_info_label = QLabel("预览: -")

        self.template_combo = QComboBox()
        for item in TemplateKind:
            self.template_combo.addItem(item.value, item)
        self.template_combo.setCurrentText(TemplateKind.LEICA_FRAME.value)

        self.position_combo = QComboBox()
        for item in WatermarkPosition:
            self.position_combo.addItem(item.value, item)
        self.position_combo.setCurrentText(WatermarkPosition.BOTTOM_RIGHT.value)

        self.title_input = QLineEdit("CODERLEEX")

        self.title_font_combo = QComboBox()
        for name, paths in TITLE_FONTS:
            if not paths or any(Path(p).exists() for p in paths):
                self.title_font_combo.addItem(name, name)

        self.title_opacity_slider = self.make_slider(5, 100, 100, suffix="%")

        self.title_offset_x_slider = self.make_slider(-50, 50, 0)
        self.title_offset_y_slider = self.make_slider(-50, 50, 0)
        self.subtitle_input = QLineEdit("")
        self.detail_template_input = QLineEdit("{camera} · {lens} · {focal} · {aperture} · {shutter} · {iso}")
        self.background_color_input = QLineEdit("#f8f7f4")
        self.use_exif_checkbox = QCheckBox("自动使用照片相机参数")
        self.use_exif_checkbox.setChecked(True)
        self.signature_text_input = QLineEdit("CODERLEEX PHOTOGRAPHY")
        self.signature_position_combo = QComboBox()
        for item in WatermarkPosition:
            self.signature_position_combo.addItem(item.value, item)
        self.signature_position_combo.setCurrentText(WatermarkPosition.BOTTOM_RIGHT.value)
        self.signature_scale_slider = self.make_slider(4, 80, 20)
        self.signature_opacity_slider = self.make_slider(5, 100, 38)
        self.logo_position_combo = QComboBox()
        for item in WatermarkPosition:
            self.logo_position_combo.addItem(item.value, item)
        self.logo_position_combo.setCurrentText(WatermarkPosition.BOTTOM_LEFT.value)
        self.logo_scale_slider = self.make_slider(4, 40, 14)
        self.logo_offset_x_slider = self.make_slider(-50, 50, 0)
        self.logo_offset_y_slider = self.make_slider(-50, 50, 0)
        self.watermark_combo = QComboBox()
        self.watermark_dir_label = QLabel()
        self.watermark_dir_label.setWordWrap(True)
        self.load_watermarks()

        self.opacity_slider = self.make_slider(5, 100, 85, suffix="%")
        self.text_scale_slider = self.make_slider(50, 220, 100)
        self.border_slider = self.make_slider(1, 16, 6)
        self.bottom_slider = self.make_slider(8, 36, 18)
        self.main_image_slider = self.make_slider(45, 100, 90)
        self.corner_radius_slider = self.make_slider(0, 18, 0)
        self.shadow_slider = self.make_slider(0, 20, 0)
        self.blur_slider = self.make_slider(5, 100, 45)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(95)

        import_button = QPushButton("导入照片")
        import_button.clicked.connect(self.choose_files)
        clear_button = QPushButton("清空照片")
        clear_button.clicked.connect(self.clear_photos)
        choose_watermark_dir_button = QPushButton("选择水印目录")
        choose_watermark_dir_button.clicked.connect(self.choose_watermark_dir)
        export_button = QPushButton("导出当前")
        export_button.clicked.connect(self.export_current)
        batch_button = QPushButton("批量导出")
        batch_button.clicked.connect(self.export_all)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        controls_layout.addWidget(scroll)

        canvas_section = CollapsibleSection("画布 / 主体", checked=True)
        camera_group = canvas_section.enable_checkbox
        canvas_section.form.addRow("水印目录", self.watermark_dir_label)
        canvas_section.form.addRow("", choose_watermark_dir_button)
        canvas_section.form.addRow("模板", self.template_combo)
        canvas_section.form.addRow("背景色", self.background_color_input)
        canvas_section.form.addRow("整体透明度", self.opacity_slider)
        canvas_section.form.addRow("主图比例", self.main_image_slider)
        canvas_section.form.addRow("边框比例", self.border_slider)
        canvas_section.form.addRow("底部留白", self.bottom_slider)
        canvas_section.form.addRow("圆角", self.corner_radius_slider)
        canvas_section.form.addRow("阴影", self.shadow_slider)
        canvas_section.form.addRow("模糊", self.blur_slider)
        scroll_layout.addWidget(canvas_section)

        title_section = CollapsibleSection("主标题", checked=True)
        self.title_group = title_section.enable_checkbox
        title_section.form.addRow("主标题", self.title_input)
        title_section.form.addRow("字体", self.title_font_combo)
        title_section.form.addRow("透明度", self.title_opacity_slider)
        title_section.form.addRow("位置", self.position_combo)
        title_section.form.addRow("文字大小", self.text_scale_slider)
        title_section.form.addRow("左右移动", self.title_offset_x_slider)
        title_section.form.addRow("上下移动", self.title_offset_y_slider)
        scroll_layout.addWidget(title_section)

        logo_section = CollapsibleSection("相机 Logo", checked=True)
        logo_group = logo_section.enable_checkbox
        logo_section.form.addRow("位置", self.logo_position_combo)
        logo_section.form.addRow("大小", self.logo_scale_slider)
        logo_section.form.addRow("左右移动", self.logo_offset_x_slider)
        logo_section.form.addRow("上下移动", self.logo_offset_y_slider)
        scroll_layout.addWidget(logo_section)

        exif_section = CollapsibleSection("EXIF 参数", checked=True)
        self.exif_group = exif_section.enable_checkbox
        self.exif_position_combo = QComboBox()
        for item in WatermarkPosition:
            self.exif_position_combo.addItem(item.value, item)
        self.exif_position_combo.setCurrentText(WatermarkPosition.BOTTOM_LEFT.value)
        self.exif_scale_slider = self.make_slider(35, 250, 100)
        self.exif_opacity_slider = self.make_slider(5, 100, 85)
        self.exif_offset_x_slider = self.make_slider(-50, 50, 0)
        self.exif_offset_y_slider = self.make_slider(-50, 50, 0)
        exif_section.form.addRow("EXIF", self.use_exif_checkbox)
        exif_section.form.addRow("副标题", self.subtitle_input)
        exif_section.form.addRow("参数模板", self.detail_template_input)
        exif_section.form.addRow("位置", self.exif_position_combo)
        exif_section.form.addRow("大小", self.exif_scale_slider)
        exif_section.form.addRow("透明度", self.exif_opacity_slider)
        exif_section.form.addRow("左右移动", self.exif_offset_x_slider)
        exif_section.form.addRow("上下移动", self.exif_offset_y_slider)
        scroll_layout.addWidget(exif_section)

        signature_section = CollapsibleSection("签名水印", checked=False)
        signature_group = signature_section.enable_checkbox
        signature_section.form.addRow("PNG 水印", self.watermark_combo)
        signature_section.form.addRow("签名文字", self.signature_text_input)
        signature_section.form.addRow("位置", self.signature_position_combo)
        signature_section.form.addRow("大小", self.signature_scale_slider)
        signature_section.form.addRow("透明度", self.signature_opacity_slider)
        self.signature_offset_x_slider = self.make_slider(-50, 50, 0)
        self.signature_offset_y_slider = self.make_slider(-50, 50, 0)
        signature_section.form.addRow("左右移动", self.signature_offset_x_slider)
        signature_section.form.addRow("上下移动", self.signature_offset_y_slider)
        scroll_layout.addWidget(signature_section)

        export_section = CollapsibleSection("导出")
        export_section.form.addRow("JPG 质量", self.quality_spin)
        scroll_layout.addWidget(export_section)
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)

        quick_export = QWidget()
        quick_export_layout = QHBoxLayout(quick_export)
        quick_export_layout.setContentsMargins(0, 8, 0, 0)
        quick_export_layout.addWidget(export_button)
        quick_export_layout.addWidget(batch_button)
        controls_layout.addWidget(quick_export)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        photo_buttons = QHBoxLayout()
        photo_buttons.addWidget(import_button)
        photo_buttons.addWidget(clear_button)
        left_layout.addLayout(photo_buttons)
        left_layout.addWidget(self.photo_count_label)
        left_layout.addWidget(self.photo_list)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(self.preview_label, 1)
        center_layout.addWidget(self.preview_info_label)
        center_layout.addWidget(self.meta_label)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(controls)
        splitter.setSizes([230, 820, 300])
        self.setCentralWidget(splitter)

        for widget in [
            self.template_combo,
            self.position_combo,
            self.title_input,
            self.title_font_combo,
            self.title_opacity_slider,
            self.subtitle_input,
            self.detail_template_input,
            self.background_color_input,
            self.use_exif_checkbox,
            camera_group,
            self.title_group,
            self.title_offset_x_slider,
            self.title_offset_y_slider,
            logo_group,
            self.logo_position_combo,
            self.logo_scale_slider,
            self.logo_offset_x_slider,
            self.logo_offset_y_slider,
            self.exif_group,
            self.exif_position_combo,
            self.exif_scale_slider,
            self.exif_opacity_slider,
            self.exif_offset_x_slider,
            self.exif_offset_y_slider,
            signature_group,
            self.signature_text_input,
            self.signature_position_combo,
            self.signature_scale_slider,
            self.signature_opacity_slider,
            self.signature_offset_x_slider,
            self.signature_offset_y_slider,
            self.watermark_combo,
            self.opacity_slider,
            self.text_scale_slider,
            self.main_image_slider,
            self.border_slider,
            self.bottom_slider,
            self.corner_radius_slider,
            self.shadow_slider,
            self.blur_slider,
            self.quality_spin,
        ]:
            self.connect_preview_signal(widget)
        self.camera_group = camera_group
        self.logo_group = logo_group
        self.signature_group = signature_group
        self.restore_render_settings()
        self.connect_render_setting_signals()
        self.logo_group.toggled.connect(self.on_logo_group_toggled)
        self.signature_group.toggled.connect(self.on_signature_group_toggled)
        self.on_logo_group_toggled(self.logo_group.isChecked())
        self.on_signature_group_toggled(self.signature_group.isChecked())
        self.restore_previous_photos()

    def make_settings_page(self, title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        back_button = QPushButton(f"< 设置  /  {title}")
        back_button.clicked.connect(lambda: self.settings_stack.setCurrentIndex(0))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addWidget(back_button)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def connect_preview_signal(self, widget) -> None:
        if isinstance(widget, (NumericSlider, QSlider, QSpinBox)):
            widget.valueChanged.connect(lambda *_: self.schedule_preview())
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda *_: self.schedule_preview())
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda *_: self.schedule_preview())
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(lambda *_: self.schedule_preview())

    def connect_render_setting_signals(self) -> None:
        for widget in self.render_setting_widgets().values():
            self.connect_save_signal(widget)

    def connect_save_signal(self, widget) -> None:
        if isinstance(widget, (NumericSlider, QSlider, QSpinBox)):
            widget.valueChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(lambda *_: self.save_render_settings())

    def render_setting_widgets(self) -> dict[str, object]:
        return {
            "template": self.template_combo,
            "title_position": self.position_combo,
            "title_text": self.title_input,
            "title_font": self.title_font_combo,
            "title_opacity": self.title_opacity_slider,
            "subtitle_text": self.subtitle_input,
            "detail_template": self.detail_template_input,
            "background_color": self.background_color_input,
            "use_exif": self.use_exif_checkbox,
            "enable_camera_info": self.camera_group,
            "show_title": self.title_group,
            "title_offset_x": self.title_offset_x_slider,
            "title_offset_y": self.title_offset_y_slider,
            "show_brand_logo": self.logo_group,
            "logo_position": self.logo_position_combo,
            "logo_scale": self.logo_scale_slider,
            "logo_offset_x": self.logo_offset_x_slider,
            "logo_offset_y": self.logo_offset_y_slider,
            "show_exif": self.exif_group,
            "exif_position": self.exif_position_combo,
            "exif_scale": self.exif_scale_slider,
            "exif_opacity": self.exif_opacity_slider,
            "exif_offset_x": self.exif_offset_x_slider,
            "exif_offset_y": self.exif_offset_y_slider,
            "enable_signature": self.signature_group,
            "signature_text": self.signature_text_input,
            "signature_position": self.signature_position_combo,
            "signature_scale": self.signature_scale_slider,
            "signature_opacity": self.signature_opacity_slider,
            "signature_offset_x": self.signature_offset_x_slider,
            "signature_offset_y": self.signature_offset_y_slider,
            "png_watermark_path": self.watermark_combo,
            "opacity": self.opacity_slider,
            "text_scale": self.text_scale_slider,
            "main_image": self.main_image_slider,
            "border": self.border_slider,
            "bottom": self.bottom_slider,
            "corner_radius": self.corner_radius_slider,
            "shadow": self.shadow_slider,
            "blur": self.blur_slider,
            "jpg_quality": self.quality_spin,
        }

    def save_render_settings(self) -> None:
        if self._restoring_settings:
            return
        self.settings.beginGroup("render")
        for key, widget in self.render_setting_widgets().items():
            if isinstance(widget, NumericSlider):
                self.settings.setValue(key, widget.value())
            elif isinstance(widget, QSpinBox):
                self.settings.setValue(key, widget.value())
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                self.settings.setValue(key, data.value if hasattr(data, "value") else data or "")
            elif isinstance(widget, QLineEdit):
                self.settings.setValue(key, widget.text())
            elif isinstance(widget, QCheckBox):
                self.settings.setValue(key, widget.isChecked())
        self.settings.endGroup()

    def restore_render_settings(self) -> None:
        self._restoring_settings = True
        self.settings.beginGroup("render")
        for key, widget in self.render_setting_widgets().items():
            if not self.settings.contains(key):
                continue
            value = self.settings.value(key)
            if isinstance(widget, NumericSlider):
                self.set_numeric_slider_value(widget, value)
            elif isinstance(widget, QSpinBox):
                self.set_spinbox_value(widget, value)
            elif isinstance(widget, QComboBox):
                self.set_combo_value(widget, value)
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(self.settings_bool(value))
        self.settings.endGroup()
        self._restoring_settings = False

    def set_numeric_slider_value(self, widget: NumericSlider, value) -> None:
        try:
            widget.setValue(float(value))
        except (TypeError, ValueError):
            return

    def set_spinbox_value(self, widget: QSpinBox, value) -> None:
        try:
            widget.setValue(int(float(value)))
        except (TypeError, ValueError):
            return

    def set_combo_value(self, widget: QComboBox, value) -> None:
        text = str(value)
        for index in range(widget.count()):
            data = widget.itemData(index)
            data_value = data.value if hasattr(data, "value") else data
            if str(data_value) == text or widget.itemText(index) == text:
                widget.setCurrentIndex(index)
                return

    def settings_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def make_slider(
        self,
        minimum: float,
        maximum: float,
        value: float,
        *,
        decimals: int = 1,
        step: float = 0.1,
        suffix: str = "",
    ) -> NumericSlider:
        return NumericSlider(minimum, maximum, value, decimals=decimals, step=step, suffix=suffix)

    def on_logo_group_toggled(self, checked: bool) -> None:
        self.logo_position_combo.setVisible(checked)
        self.logo_scale_slider.setVisible(checked)
        self.logo_offset_x_slider.setVisible(checked)
        self.logo_offset_y_slider.setVisible(checked)
        self.schedule_preview()

    def on_signature_group_toggled(self, checked: bool) -> None:
        self.watermark_combo.setVisible(checked)
        self.signature_text_input.setVisible(checked)
        self.signature_position_combo.setVisible(checked)
        self.signature_scale_slider.setVisible(checked)
        self.signature_opacity_slider.setVisible(checked)
        self.schedule_preview()

    def load_watermarks(self) -> None:
        self.watermark_combo.clear()
        self.watermark_combo.addItem("无", "")
        self.watermark_dir_label.setText(str(self.watermark_dir))
        if self.watermark_dir.exists():
            for path in sorted(self.watermark_dir.glob("*.png")):
                if path.name.startswith("ChatGPT Image"):
                    continue
                self.watermark_combo.addItem(path.name, str(path))

    def restore_watermark_selection(self) -> None:
        self.settings.beginGroup("render")
        value = self.settings.value("png_watermark_path", "")
        self.settings.endGroup()
        self.set_combo_value(self.watermark_combo, value)

    def choose_watermark_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择水印素材目录", str(self.watermark_dir))
        if not directory:
            return
        self.watermark_dir = Path(directory)
        self.settings.setValue("watermark_dir", str(self.watermark_dir))
        self.load_watermarks()
        self.restore_watermark_selection()
        self.schedule_preview()

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择照片（可多选）",
            str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.tif *.tiff *.webp)",
        )
        self.add_files(files)

    def add_files(self, files: list[str]) -> None:
        added = False
        for raw in files:
            path = Path(raw)
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path not in self.photo_paths:
                self.photo_paths.append(path)
                item = QListWidgetItem(path.name)
                item.setData(Qt.UserRole, str(path))
                self.photo_list.addItem(item)
                added = True
        self.update_photo_count()
        if added:
            self.save_photo_paths()
        if added and self.photo_list.currentRow() < 0:
            self.photo_list.setCurrentRow(0)

    def clear_photos(self) -> None:
        self.photo_paths.clear()
        self.photo_list.clear()
        self.photo_count_label.setText("已选择 0 张照片")
        self.preview_label.clear()
        self.preview_label.setText("拖入照片或点击导入")
        self.preview_info_label.setText("预览: -")
        self.meta_label.setText("EXIF: -")
        self.settings.remove("photo_paths")

    def restore_previous_photos(self) -> None:
        raw_paths = self.settings.value("photo_paths", [])
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        existing_paths = [path for path in raw_paths if Path(path).is_file() and Path(path).suffix.lower() in IMAGE_EXTENSIONS]
        if existing_paths:
            self.add_files(existing_paths)

    def save_photo_paths(self) -> None:
        self.settings.setValue("photo_paths", [str(path) for path in self.photo_paths])

    def update_photo_count(self) -> None:
        self.photo_count_label.setText(f"已选择 {len(self.photo_paths)} 张照片")

    def on_photo_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        path = Path(current.data(Qt.UserRole))
        self.current_metadata = read_photo_metadata(path)
        detail = self.current_metadata.detail_label or "未读取到 EXIF 相机信息，可手动填写副标题"
        extra = " · ".join(
            part
            for part in [
                self.current_metadata.focal_length_35mm and f"等效 {self.current_metadata.focal_length_35mm}",
                self.current_metadata.exposure_program,
                self.current_metadata.exposure_compensation,
                self.current_metadata.metering_mode,
                self.current_metadata.white_balance,
            ]
            if part
        )
        if extra:
            detail = f"{detail} · {extra}" if detail else extra
        self.meta_label.setText(f"EXIF: {detail}")
        self.schedule_preview()

    def schedule_preview(self) -> None:
        self.preview_timer.start(120)

    def current_photo(self) -> Path | None:
        item = self.photo_list.currentItem()
        if item is None:
            return None
        return Path(item.data(Qt.UserRole))

    def collect_options(self) -> RenderOptions:
        return RenderOptions(
            template=self.template_combo.currentData(),
            position=self.position_combo.currentData(),
            title_text=self.title_input.text(),
            title_font_name=self.title_font_combo.currentData() or "",
            title_opacity=self.title_opacity_slider.value() / 100,
            subtitle_text=self.subtitle_input.text(),
            enable_camera_info=self.camera_group.isChecked(),
            enable_signature=self.signature_group.isChecked(),
            signature_text=self.signature_text_input.text(),
            signature_position=self.signature_position_combo.currentData(),
            signature_scale=self.signature_scale_slider.value() / 100,
            signature_opacity=self.signature_opacity_slider.value() / 100,
            signature_offset_x_percent=self.signature_offset_x_slider.value() / 100,
            signature_offset_y_percent=self.signature_offset_y_slider.value() / 100,
            use_exif=self.use_exif_checkbox.isChecked(),
            show_title=self.title_group.isChecked(),
            title_position=self.position_combo.currentData(),
            title_offset_x_percent=self.title_offset_x_slider.value() / 100,
            title_offset_y_percent=self.title_offset_y_slider.value() / 100,
            show_exif=self.exif_group.isChecked(),
            exif_position=self.exif_position_combo.currentData(),
            exif_scale=self.exif_scale_slider.value() / 100,
            exif_opacity=self.exif_opacity_slider.value() / 100,
            exif_offset_x_percent=self.exif_offset_x_slider.value() / 100,
            exif_offset_y_percent=self.exif_offset_y_slider.value() / 100,
            show_brand_logo=self.logo_group.isChecked(),
            logo_position=self.logo_position_combo.currentData(),
            logo_scale=self.logo_scale_slider.value() / 100,
            logo_offset_x_percent=self.logo_offset_x_slider.value() / 100,
            logo_offset_y_percent=self.logo_offset_y_slider.value() / 100,
            detail_template=self.detail_template_input.text(),
            text_scale=self.text_scale_slider.value() / 100,
            opacity=self.opacity_slider.value() / 100,
            border_percent=self.border_slider.value() / 100,
            bottom_percent=self.bottom_slider.value() / 100,
            main_image_percent=self.main_image_slider.value() / 100,
            corner_radius_percent=self.corner_radius_slider.value() / 100,
            shadow_percent=self.shadow_slider.value() / 100,
            blur_percent=self.blur_slider.value() / 100,
            background_color=self.background_color_input.text(),
            jpg_quality=self.quality_spin.value(),
            png_watermark_path=self.watermark_combo.currentData(),
        )

    def update_preview(self) -> None:
        path = self.current_photo()
        if path is None:
            return
        try:
            target_edge = max(
                640,
                min(
                    PREVIEW_MAX_SOURCE_EDGE,
                    int(max(self.preview_label.width(), self.preview_label.height()) * 1.5),
                ),
            )
            rendered = render_image(path, self.collect_options(), self.current_metadata, max_source_edge=target_edge)
            original_size = rendered.size
            preview = rendered.copy()
            preview.thumbnail((self.preview_label.width() - 24, self.preview_label.height() - 24), resample=Image.Resampling.LANCZOS)
            pixmap = QPixmap.fromImage(ImageQt(preview.convert("RGBA")))
            self.preview_label.setPixmap(pixmap)
            self.preview_info_label.setText(
                f"预览: {preview.width} x {preview.height}    渲染: {original_size[0]} x {original_size[1]}    导出使用原图"
            )
        except Exception as exc:
            self.preview_label.setText(f"预览失败: {exc}")

    def export_current(self) -> None:
        path = self.current_photo()
        if path is None:
            QMessageBox.information(self, "没有照片", "请先导入一张照片。")
            return
        default = path.with_name(f"{path.stem}_watermarked.jpg")
        output, _ = QFileDialog.getSaveFileName(self, "导出照片", str(default), "JPEG (*.jpg);;PNG (*.png)")
        if not output:
            return
        self.export_one(path, Path(output))
        QMessageBox.information(self, "已导出", str(output))

    def export_all(self) -> None:
        if not self.photo_paths:
            QMessageBox.information(self, "没有照片", "请先导入照片。")
            return
        directory = QFileDialog.getExistingDirectory(self, "选择批量导出目录", str(Path.home()))
        if not directory:
            return
        output_dir = Path(directory)
        for path in self.photo_paths:
            output = output_dir / f"{path.stem}_watermarked.jpg"
            metadata = read_photo_metadata(path)
            rendered = render_image(path, self.collect_options(), metadata)
            save_rendered(rendered, output, self.quality_spin.value())
        QMessageBox.information(self, "批量导出完成", f"已导出 {len(self.photo_paths)} 张照片。")

    def export_one(self, source: Path, output: Path) -> None:
        rendered = render_image(source, self.collect_options(), read_photo_metadata(source))
        save_rendered(rendered, output, self.quality_spin.value())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.schedule_preview()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
