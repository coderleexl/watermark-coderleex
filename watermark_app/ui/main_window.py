from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, QRect, QSize, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel as QLabel,
    CaptionLabel,
    CheckBox as QCheckBox,
    ComboBox as QComboBox,
    OpacityAniStackedWidget,
    FluentIcon,
    FluentTitleBar,
    FluentWindow,
    LineEdit as QLineEdit,
    ListWidget as QListWidget,
    PrimaryPushButton,
    ProgressBar as QProgressBar,
    PushButton as QPushButton,
    SegmentedWidget,
    Slider as QSlider,
    SpinBox as QSpinBox,
    Theme,
    TitleLabel,
    TreeWidget as QTreeWidget,
    setTheme,
    setThemeColor,
)

from watermark_app.core.collage import CollageEngine
from watermark_app.core.collage_groups import (
    CollageGroup,
    CollageGroupStore,
    layout_by_name,
    safe_filename,
    timestamp,
)
from watermark_app.core.exif import PhotoMetadata, read_photo_metadata
from watermark_app.core.presets import Preset, PresetManager
from watermark_app.core.renderer import render_image, save_rendered, TITLE_FONTS
from watermark_app.core.templates import BlurStyle, RenderOptions, TemplateKind, WatermarkPosition
from watermark_app.ui.collage_panel import CollagePanel
from watermark_app.ui.collage_selector import CollagePhotoSelector
from watermark_app.ui.common import CollapsibleSection, NumericSlider, make_settings_page


LEGACY_WATERMARK_DIR = Path("/Users/lixinglin/Documents/水印")
WATERMARK_DIR = Path(__file__).resolve().parents[2] / "waterTmp"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
PREVIEW_MAX_SOURCE_EDGE = 1400
EXIF_FIELD_OPTIONS = [
    ("camera", "相机"),
    ("lens", "镜头"),
    ("focal", "焦距"),
    ("aperture", "光圈"),
    ("shutter", "快门"),
    ("iso", "ISO"),
    ("date", "日期"),
    ("focal35", "等效焦距"),
    ("mode", "模式"),
    ("ev", "曝光补偿"),
    ("metering", "测光"),
    ("wb", "白平衡"),
]
DEFAULT_EXIF_FIELDS = ["camera", "lens", "focal", "aperture", "shutter", "iso"]
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


class DropTreeWidget(QTreeWidget):
    def __init__(self, on_files_dropped):
        super().__init__()
        self.on_files_dropped = on_files_dropped
        self.setAcceptDrops(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        self.on_files_dropped(paths)
        event.acceptProposedAction()


class ExifFieldList(QWidget):
    valueChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.model().rowsMoved.connect(lambda *_: self.valueChanged.emit())
        for key, label in EXIF_FIELD_OPTIONS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            item.setCheckState(Qt.Checked if key in DEFAULT_EXIF_FIELDS else Qt.Unchecked)
            self.list_widget.addItem(item)
        self.list_widget.itemChanged.connect(lambda *_: self.valueChanged.emit())
        self.hint_label = CaptionLabel("拖拽可调整顺序，勾选控制显示字段")
        self.hint_label.setObjectName("mutedLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.list_widget)

    def selected_fields(self) -> list[str]:
        fields: list[str] = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == Qt.Checked:
                fields.append(str(item.data(Qt.UserRole)))
        return fields

    def set_selected_fields(self, fields: list[str]) -> None:
        known_items: dict[str, QListWidgetItem] = {}
        for index in range(self.list_widget.count()):
            item = self.list_widget.takeItem(0)
            known_items[str(item.data(Qt.UserRole))] = item
        ordered_keys = [key for key in fields if key in known_items]
        ordered_keys.extend(key for key, _ in EXIF_FIELD_OPTIONS if key in known_items and key not in ordered_keys)
        for key in ordered_keys:
            item = known_items[key]
            item.setCheckState(Qt.Checked if key in fields else Qt.Unchecked)
            self.list_widget.addItem(item)
        self.valueChanged.emit()

    def template_text(self) -> str:
        fields = self.selected_fields() or DEFAULT_EXIF_FIELDS
        return " · ".join(f"{{{field}}}" for field in fields)

    def serialized_value(self) -> str:
        return ",".join(self.selected_fields())

    def restore_serialized_value(self, value) -> None:
        text = str(value or "")
        fields = [field.strip() for field in text.split(",") if field.strip()]
        self.set_selected_fields(fields or DEFAULT_EXIF_FIELDS)

    def move_current(self, direction: int) -> None:
        row = self.list_widget.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.list_widget.count():
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(target, item)
        self.list_widget.setCurrentRow(target)
        self.valueChanged.emit()


class MacFluentTitleBar(FluentTitleBar):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.iconLabel.hide()
        self.titleLabel.hide()
        for button in [self.minBtn, self.maxBtn, self.closeBtn]:
            self.buttonLayout.removeWidget(button)
        self.buttonLayout.addWidget(self.closeBtn)
        self.buttonLayout.addWidget(self.minBtn)
        self.buttonLayout.addWidget(self.maxBtn)
        self.hBoxLayout.removeItem(self.vBoxLayout)
        self.hBoxLayout.insertLayout(0, self.vBoxLayout, 0)
        self.hBoxLayout.insertSpacing(1, 90)


class ExportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int, int, bool, str)

    def __init__(self, jobs: list[tuple[Path, Path, RenderOptions]]) -> None:
        super().__init__()
        self.jobs = jobs
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        total = len(self.jobs)
        completed = 0
        errors: list[str] = []
        for index, (source, output, options) in enumerate(self.jobs, start=1):
            if self.cancel_requested:
                break
            self.progress.emit(index - 1, total, source.name)
            try:
                metadata = read_photo_metadata(source)
                rendered = render_image(source, options, metadata)
                save_rendered(rendered, output, options.jpg_quality)
                completed += 1
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")
        canceled = self.cancel_requested
        message = "\n".join(errors[:5])
        if len(errors) > 5:
            message += f"\n... 还有 {len(errors) - 5} 个错误"
        self.progress.emit(completed, total, "完成" if not canceled else "已取消")
        self.finished.emit(completed, total, canceled, message)


class CollagePreviewWorker(QObject):
    finished = Signal(int, object, str, str, int, int, tuple)

    def __init__(self, request_id: int, paths: list[Path], layout, options, max_source_edge: int) -> None:
        super().__init__()
        self.request_id = request_id
        self.paths = paths
        self.layout = layout
        self.options = options
        self.max_source_edge = max_source_edge

    def run(self) -> None:
        try:
            image = CollageEngine().create_collage_from_paths(
                self.paths,
                self.layout,
                self.options,
                max_source_edge=self.max_source_edge,
            )
            self.finished.emit(
                self.request_id,
                image,
                "",
                self.layout.name,
                len(self.paths),
                self.layout.cell_count,
                image.size,
            )
        except Exception as exc:
            self.finished.emit(
                self.request_id,
                None,
                str(exc),
                self.layout.name,
                len(self.paths),
                self.layout.cell_count,
                (0, 0),
            )


class CollageBatchExportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int, int, bool, str)

    def __init__(self, jobs: list[tuple[CollageGroup, Path, int]]) -> None:
        super().__init__()
        self.jobs = jobs
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        total = len(self.jobs)
        completed = 0
        errors: list[str] = []
        engine = CollageEngine()
        for index, (group, output, quality) in enumerate(self.jobs, start=1):
            if self.cancel_requested:
                break
            self.progress.emit(index - 1, total, group.name)
            try:
                paths = [Path(path) for path in group.photo_paths]
                image = engine.create_collage_from_paths(paths, layout_by_name(group.layout_name), group.options)
                save_rendered(image, output, quality)
                completed += 1
            except Exception as exc:
                errors.append(f"{group.name}: {exc}")
        canceled = self.cancel_requested
        message = "\n".join(errors[:5])
        if len(errors) > 5:
            message += f"\n... 还有 {len(errors) - 5} 个错误"
        self.progress.emit(completed, total, "完成" if not canceled else "已取消")
        self.finished.emit(completed, total, canceled, message)


class ExportProgressDialog(QDialog):
    cancelRequested = Signal()

    def __init__(self, total: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出中")
        self.setModal(False)
        self.setMinimumWidth(380)
        self.status_label = QLabel("准备导出...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(0)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.on_cancel_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

    def update_progress(self, completed: int, total: int, name: str) -> None:
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(completed)
        self.status_label.setText(f"{completed} / {total}    {name}")

    def on_cancel_clicked(self) -> None:
        self.cancel_button.setEnabled(False)
        self.status_label.setText("正在取消，当前图片导出完成后停止...")
        self.cancelRequested.emit()

    def reject(self) -> None:
        self.on_cancel_clicked()


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        if sys.platform == "darwin":
            self.setTitleBar(MacFluentTitleBar(self))
            self.navigationInterface.panel.vBoxLayout.setContentsMargins(0, 48, 0, 5)
        #self.setWindowTitle("Coderleex Watermark")
        self.resize(1560, 940)

        self.photo_paths: list[Path] = []
        self.current_metadata = PhotoMetadata()
        self.settings = QSettings("coderleex", "watermark")
        self._restoring_settings = False
        self._restoring_collage_settings = False
        self.current_ratio_key = "default"
        self.ratio_groups: dict[str, QTreeWidgetItem] = {}
        self.apply_saved_theme()
        self.export_thread: QThread | None = None
        self.export_worker: ExportWorker | None = None
        self.export_dialog: ExportProgressDialog | None = None
        self.collage_preview_request_id = 0
        self.collage_preview_jobs: list[tuple[QThread, CollagePreviewWorker]] = []
        self.collage_batch_thread: QThread | None = None
        self.collage_batch_worker: CollageBatchExportWorker | None = None
        self.collage_batch_dialog: ExportProgressDialog | None = None
        self.collage_group_store = CollageGroupStore()
        self.current_collage_group_id = ""
        self.collage_dirty = False
        self._loading_collage_group = False
        self.watermark_dir = self.initial_watermark_dir()
        self.preset_manager = PresetManager(self.settings)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_preview)
        self.collage_engine = CollageEngine()
        self.collage_preview_timer = QTimer(self)
        self.collage_preview_timer.setSingleShot(True)
        self.collage_preview_timer.timeout.connect(self.update_collage_preview)

        self.photo_list = DropTreeWidget(self.add_files)
        self.photo_list.currentItemChanged.connect(self.on_photo_changed)
        self.photo_count_label = CaptionLabel("已选择 0 张照片")
        self.photo_count_label.setObjectName("mutedLabel")

        self.preview_label = QLabel("拖入照片或点击导入")
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)

        self.meta_label = CaptionLabel("EXIF: -")
        self.meta_label.setObjectName("mutedLabel")
        self.meta_label.setWordWrap(True)
        self.preview_info_label = CaptionLabel("预览: -")
        self.preview_info_label.setObjectName("mutedLabel")

        self.appearance_theme_combo = QComboBox()
        self.appearance_theme_combo.addItem("跟随系统", userData="AUTO")
        self.appearance_theme_combo.addItem("浅色", userData="LIGHT")
        self.appearance_theme_combo.addItem("深色", userData="DARK")
        self.set_combo_value(self.appearance_theme_combo, self.settings.value("appearance/theme", "AUTO"))

        self.theme_color_combo = QComboBox()
        for label, color in [
            ("金色", "#c9973f"),
            ("蓝色", "#4a9eff"),
            ("绿色", "#2f9e65"),
            ("红色", "#d94848"),
            ("紫色", "#7950f2"),
            ("灰色", "#5c6370"),
        ]:
            self.theme_color_combo.addItem(label, userData=color)
        self.set_combo_value(self.theme_color_combo, self.settings.value("appearance/theme_color", "#c9973f"))

        self.template_combo = QComboBox()
        for item in TemplateKind:
            self.template_combo.addItem(item.value, userData=item)
        self.template_combo.setCurrentText(TemplateKind.LEICA_FRAME.value)

        self.blur_style_combo = QComboBox()
        for item in BlurStyle:
            self.blur_style_combo.addItem(item.value, userData=item)
        self.blur_style_combo.setCurrentText(BlurStyle.GAUSSIAN.value)

        self.preset_combo = QComboBox()
        self.save_preset_button = QPushButton("保存预设")
        self.delete_preset_button = QPushButton("删除预设")

        self.position_combo = QComboBox()
        for item in WatermarkPosition:
            self.position_combo.addItem(item.value, userData=item)
        self.position_combo.setCurrentText(WatermarkPosition.BOTTOM_RIGHT.value)

        self.title_input = QLineEdit()
        self.title_input.setText("CODERLEEX")

        self.title_font_combo = QComboBox()
        for name, paths in TITLE_FONTS:
            if not paths or any(Path(p).exists() for p in paths):
                self.title_font_combo.addItem(name, userData=name)

        self.title_opacity_slider = self.make_slider(5, 100, 100, suffix="%")

        self.title_offset_x_slider = self.make_slider(-50, 50, 0)
        self.title_offset_y_slider = self.make_slider(-50, 50, 0)
        self.background_color_input = QLineEdit()
        self.background_color_input.setText("#f8f7f4")
        self.use_exif_checkbox = QCheckBox("自动使用照片相机参数")
        self.use_exif_checkbox.setChecked(True)
        self.exif_field_list = ExifFieldList()
        self.subtitle_input = QLineEdit()
        self.subtitle_input.setPlaceholderText("副标题")
        self.exif_position_combo = QComboBox()
        for item in WatermarkPosition:
            self.exif_position_combo.addItem(item.value, userData=item)
        self.exif_position_combo.setCurrentText(WatermarkPosition.BOTTOM_LEFT.value)
        self.exif_scale_slider = NumericSlider(35, 250, 100)
        self.exif_opacity_slider = NumericSlider(5, 100, 85)
        self.exif_line_spacing_slider = NumericSlider(0, 200, 25)
        self.exif_second_line_indent_slider = NumericSlider(-20, 80, 0)
        self.exif_offset_x_slider = NumericSlider(-50, 50, 0)
        self.exif_offset_y_slider = NumericSlider(-50, 50, 0)
        self.signature_text_input = QLineEdit()
        self.signature_text_input.setText("CODERLEEX PHOTOGRAPHY")
        self.signature_position_combo = QComboBox()
        for item in WatermarkPosition:
            self.signature_position_combo.addItem(item.value, userData=item)
        self.signature_position_combo.setCurrentText(WatermarkPosition.BOTTOM_RIGHT.value)
        self.signature_scale_slider = self.make_slider(4, 80, 20)
        self.signature_opacity_slider = self.make_slider(5, 100, 38)
        self.logo_position_combo = QComboBox()
        for item in WatermarkPosition:
            self.logo_position_combo.addItem(item.value, userData=item)
        self.logo_position_combo.setCurrentText(WatermarkPosition.BOTTOM_LEFT.value)
        self.logo_scale_slider = self.make_slider(4, 40, 14)
        self.logo_offset_x_slider = self.make_slider(-50, 50, 0)
        self.logo_offset_y_slider = self.make_slider(-50, 50, 0)
        self.watermark_combo = QComboBox()
        self.watermark_dir_label = CaptionLabel()
        self.watermark_dir_label.setObjectName("mutedLabel")
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
        self.quality_spin.setSymbolVisible(False)

        import_button = QPushButton("导入照片")
        import_button.clicked.connect(self.choose_files)
        clear_button = QPushButton("清空照片")
        clear_button.clicked.connect(self.clear_photos)
        choose_watermark_dir_button = QPushButton("选择水印目录")
        choose_watermark_dir_button.clicked.connect(self.choose_watermark_dir)
        export_button = PrimaryPushButton("导出当前")
        export_button.clicked.connect(self.export_current)
        batch_button = QPushButton("批量导出")
        batch_button.clicked.connect(self.export_all)

        page = QWidget()
        page.setObjectName("watermarkPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 8, 16, 16)
        page_layout.setSpacing(10)
        page_layout.addWidget(TitleLabel("Coderleex Watermark"))

        controls = QWidget()
        controls.setObjectName("settingsPanel")
        controls.setMinimumWidth(420)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        settings_tabs = SegmentedWidget()
        settings_stack = OpacityAniStackedWidget()
        settings_stack.setObjectName("settingsStack")
        controls_layout.addWidget(settings_tabs)
        controls_layout.addWidget(settings_stack, 1)

        canvas_section = CollapsibleSection("画布 / 主体", checked=True)
        camera_group = canvas_section.enable_checkbox
        canvas_section.form.addRow("水印目录", self.watermark_dir_label)
        canvas_section.form.addRow("", choose_watermark_dir_button)
        canvas_section.form.addRow("模板", self.template_combo)

        preset_row = QWidget()
        preset_row_layout = QHBoxLayout(preset_row)
        preset_row_layout.setContentsMargins(0, 0, 0, 0)
        preset_row_layout.setSpacing(4)
        preset_row_layout.addWidget(self.preset_combo, 1)
        preset_row_layout.addWidget(self.save_preset_button)
        preset_row_layout.addWidget(self.delete_preset_button)
        canvas_section.form.addRow("预设", preset_row)
        canvas_section.form.addRow("模糊样式", self.blur_style_combo)
        canvas_section.form.addRow("背景色", self.background_color_input)
        canvas_section.form.addRow("整体透明度", self.opacity_slider)
        canvas_section.form.addRow("主图比例", self.main_image_slider)
        canvas_section.form.addRow("边框比例", self.border_slider)
        canvas_section.form.addRow("底部留白", self.bottom_slider)
        canvas_section.form.addRow("圆角", self.corner_radius_slider)
        canvas_section.form.addRow("阴影", self.shadow_slider)
        canvas_section.form.addRow("模糊", self.blur_slider)

        title_section = CollapsibleSection("主标题", checked=True)
        self.title_group = title_section.enable_checkbox
        title_section.form.addRow("主标题", self.title_input)
        title_section.form.addRow("字体", self.title_font_combo)
        title_section.form.addRow("透明度", self.title_opacity_slider)
        title_section.form.addRow("位置", self.position_combo)
        title_section.form.addRow("文字大小", self.text_scale_slider)
        title_section.form.addRow("左右移动", self.title_offset_x_slider)
        title_section.form.addRow("上下移动", self.title_offset_y_slider)

        logo_section = CollapsibleSection("相机 Logo", checked=True)
        logo_group = logo_section.enable_checkbox
        logo_section.form.addRow("位置", self.logo_position_combo)
        logo_section.form.addRow("大小", self.logo_scale_slider)
        logo_section.form.addRow("左右移动", self.logo_offset_x_slider)
        logo_section.form.addRow("上下移动", self.logo_offset_y_slider)

        exif_section = CollapsibleSection("EXIF 参数", checked=True)
        self.exif_group = exif_section.enable_checkbox
        exif_section.form.addRow("EXIF", self.use_exif_checkbox)
        exif_section.form.addRow("副标题", self.subtitle_input)
        exif_section.form.addRow("位置", self.exif_position_combo)
        exif_section.form.addRow("大小", self.exif_scale_slider)
        exif_section.form.addRow("透明度", self.exif_opacity_slider)
        exif_section.form.addRow("行间距", self.exif_line_spacing_slider)
        exif_section.form.addRow("第二行缩进", self.exif_second_line_indent_slider)
        exif_section.form.addRow("左右移动", self.exif_offset_x_slider)
        exif_section.form.addRow("上下移动", self.exif_offset_y_slider)

        exif_field_section = CollapsibleSection("EXIF 字段")
        exif_field_section.form.addRow(self.exif_field_list)

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

        export_section = CollapsibleSection("导出")
        export_section.form.addRow("JPG 质量", self.quality_spin)

        appearance_section = CollapsibleSection("外观")
        appearance_section.form.addRow("主题", self.appearance_theme_combo)
        appearance_section.form.addRow("主题色", self.theme_color_combo)

        setting_pages = [
            ("canvas", "画布", make_settings_page(canvas_section)),
            ("title", "标题", make_settings_page(title_section)),
            ("camera", "相机", make_settings_page(logo_section)),
            ("exif", "EXIF", make_settings_page(exif_section, exif_field_section)),
            ("signature", "签名", make_settings_page(signature_section)),
            ("export", "导出", make_settings_page(export_section)),
            ("appearance", "外观", make_settings_page(appearance_section)),
        ]
        for index, (route, label, page_widget) in enumerate(setting_pages):
            settings_stack.addWidget(page_widget)
            settings_tabs.addItem(route, label, onClick=lambda _, i=index: settings_stack.setCurrentIndex(i))
        settings_tabs.setCurrentItem("canvas")
        settings_stack.setCurrentIndex(0)

        quick_export = QWidget()
        quick_export_layout = QHBoxLayout(quick_export)
        quick_export_layout.setContentsMargins(4, 10, 4, 4)
        quick_export_layout.setSpacing(8)
        quick_export_layout.addWidget(export_button)
        quick_export_layout.addWidget(batch_button)
        controls_layout.addWidget(quick_export)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        photo_buttons = QHBoxLayout()
        photo_buttons.setSpacing(6)
        photo_buttons.addWidget(import_button)
        photo_buttons.addWidget(clear_button)
        left_layout.addLayout(photo_buttons)
        left_layout.addWidget(self.photo_count_label)
        left_layout.addWidget(self.photo_list, 1)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        center_layout.addWidget(self.preview_label, 1)
        center_layout.addWidget(self.preview_info_label)
        center_layout.addWidget(self.meta_label)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(controls)
        splitter.setSizes([250, 880, 440])
        splitter.setHandleWidth(3)
        page_layout.addWidget(splitter, 1)
        self.addSubInterface(page, FluentIcon.PHOTO, "水印")
        self.addSubInterface(self.create_collage_page(), FluentIcon.ALBUM, "拼图")
        self.refresh_theme_styles()

        for widget in [
            self.template_combo,
            self.appearance_theme_combo,
            self.theme_color_combo,
            self.blur_style_combo,
            self.position_combo,
            self.title_input,
            self.title_font_combo,
            self.title_opacity_slider,
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
        self.connect_exif_signals()
        self.restore_render_settings()
        self.connect_render_setting_signals()
        self.appearance_theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        self.theme_color_combo.currentIndexChanged.connect(self.on_theme_changed)
        self.template_combo.currentIndexChanged.connect(self.on_template_changed)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        self.save_preset_button.clicked.connect(self.save_current_preset)
        self.delete_preset_button.clicked.connect(self.delete_current_preset)
        self.logo_group.toggled.connect(self.on_logo_group_toggled)
        self.signature_group.toggled.connect(self.on_signature_group_toggled)
        self.on_template_changed()
        self.on_logo_group_toggled(self.logo_group.isChecked())
        self.on_signature_group_toggled(self.signature_group.isChecked())
        self.restore_previous_photos()

    def initial_watermark_dir(self) -> Path:
        configured = Path(self.settings.value("watermark_dir", str(WATERMARK_DIR)))
        if configured == LEGACY_WATERMARK_DIR or not configured.exists():
            self.settings.setValue("watermark_dir", str(WATERMARK_DIR))
            return WATERMARK_DIR
        return configured

    def apply_saved_theme(self) -> None:
        mode = str(self.settings.value("appearance/theme", "AUTO"))
        color = str(self.settings.value("appearance/theme_color", "#c9973f"))
        self.apply_fluent_theme(mode, color)

    def on_theme_changed(self) -> None:
        mode = self.appearance_theme_combo.currentData() or "AUTO"
        color = self.theme_color_combo.currentData() or "#c9973f"
        self.settings.setValue("appearance/theme", mode)
        self.settings.setValue("appearance/theme_color", color)
        self.apply_fluent_theme(str(mode), str(color))
        self.refresh_theme_styles()

    def apply_fluent_theme(self, mode: str, color: str) -> None:
        theme = {
            "LIGHT": Theme.LIGHT,
            "DARK": Theme.DARK,
            "AUTO": Theme.AUTO,
        }.get(mode, Theme.AUTO)
        setTheme(theme, lazy=False)
        setThemeColor(color)

    def current_theme_is_dark(self) -> bool:
        mode = str(self.settings.value("appearance/theme", "AUTO"))
        return mode != "LIGHT"

    def refresh_theme_styles(self) -> None:
        self.apply_window_style()
        widgets = [
            getattr(self, "photo_count_label", None),
            getattr(self, "preview_label", None),
            getattr(self, "meta_label", None),
            getattr(self, "preview_info_label", None),
            getattr(self, "watermark_dir_label", None),
            getattr(self, "collage_preview_label", None),
            getattr(self, "collage_status_label", None),
        ]
        for widget in widgets:
            if widget is not None:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

    def create_collage_page(self) -> QWidget:
        self.collage_selector = CollagePhotoSelector(IMAGE_EXTENSIONS)
        self.collage_panel = CollagePanel()
        self.collage_panel.optionsChanged.connect(self.schedule_collage_preview)
        self.collage_panel.optionsChanged.connect(self.save_collage_settings)
        self.collage_panel.optionsChanged.connect(self.mark_collage_dirty)
        self.collage_selector.collage_order_changed.connect(lambda *_: self.schedule_collage_preview())
        self.collage_selector.collage_order_changed.connect(lambda *_: self.mark_collage_dirty())

        import_button = QPushButton("导入照片")
        import_button.clicked.connect(self.choose_collage_files)
        clear_button = QPushButton("清空照片")
        clear_button.clicked.connect(self.clear_collage_photos)
        export_button = QPushButton("导出当前")
        export_button.clicked.connect(self.export_collage)
        add_group_button = PrimaryPushButton("暂存为组")
        add_group_button.clicked.connect(self.add_collage_group)
        update_group_button = QPushButton("更新组")
        update_group_button.clicked.connect(self.update_current_collage_group)
        rename_group_button = QPushButton("重命名")
        rename_group_button.clicked.connect(self.rename_current_collage_group)
        copy_group_button = QPushButton("复制组")
        copy_group_button.clicked.connect(self.copy_current_collage_group)
        delete_group_button = QPushButton("删除组")
        delete_group_button.clicked.connect(self.delete_current_collage_group)
        batch_export_button = QPushButton("批量导出组")
        batch_export_button.clicked.connect(self.export_collage_groups)
        self.collage_export_format_combo = QComboBox()
        self.collage_export_format_combo.addItem("JPG", userData=".jpg")
        self.collage_export_format_combo.addItem("PNG", userData=".png")

        page = QWidget()
        page.setObjectName("collagePage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 8, 16, 16)
        page_layout.setSpacing(10)
        page_layout.addWidget(TitleLabel("Coderleex Collage"))

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        button_row.addWidget(import_button)
        button_row.addWidget(clear_button)
        left_layout.addLayout(button_row)
        left_layout.addWidget(self.collage_selector, 1)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        self.collage_preview_label = QLabel("请选择参与拼图的照片")
        self.collage_preview_label.setObjectName("previewLabel")
        self.collage_preview_label.setAlignment(Qt.AlignCenter)
        self.collage_preview_label.setMinimumSize(640, 480)
        self.collage_status_label = CaptionLabel("拼图: -")
        self.collage_status_label.setObjectName("mutedLabel")
        center_layout.addWidget(self.collage_preview_label, 1)
        center_layout.addWidget(self.collage_status_label)

        controls = QWidget()
        controls.setObjectName("settingsPanel")
        controls.setMinimumWidth(420)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self.collage_panel, 1)

        self.collage_group_list = QListWidget()
        self.collage_group_list.setIconSize(QSize(96, 64))
        self.collage_group_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.collage_group_list.setDefaultDropAction(Qt.MoveAction)
        self.collage_group_list.currentItemChanged.connect(self.on_collage_group_selected)
        self.collage_group_list.model().rowsMoved.connect(lambda *_: self.on_collage_group_rows_moved())
        group_label = CaptionLabel("拼图组")
        group_label.setObjectName("mutedLabel")
        group_buttons_1 = QHBoxLayout()
        group_buttons_1.setSpacing(6)
        group_buttons_1.addWidget(add_group_button)
        group_buttons_1.addWidget(update_group_button)
        group_buttons_2 = QHBoxLayout()
        group_buttons_2.setSpacing(6)
        group_buttons_2.addWidget(rename_group_button)
        group_buttons_2.addWidget(copy_group_button)
        group_buttons_2.addWidget(delete_group_button)
        group_buttons_3 = QHBoxLayout()
        group_buttons_3.setSpacing(6)
        group_buttons_3.addWidget(self.collage_export_format_combo)
        group_buttons_3.addWidget(export_button)
        group_buttons_3.addWidget(batch_export_button)
        controls_layout.addWidget(group_label)
        controls_layout.addWidget(self.collage_group_list, 1)
        controls_layout.addLayout(group_buttons_1)
        controls_layout.addLayout(group_buttons_2)
        controls_layout.addLayout(group_buttons_3)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(controls)
        splitter.setSizes([300, 860, 400])
        splitter.setHandleWidth(3)
        page_layout.addWidget(splitter, 1)
        self.restore_collage_settings()
        self.restore_collage_photos()
        self.restore_collage_groups()
        return page

    def save_collage_settings(self) -> None:
        if self._restoring_collage_settings or not hasattr(self, "collage_panel"):
            return
        self.settings.beginGroup("collage")
        for key, value in self.collage_panel.settings_values().items():
            self.settings.setValue(key, value)
        self.settings.endGroup()

    def restore_collage_settings(self) -> None:
        if not hasattr(self, "collage_panel"):
            return
        self._restoring_collage_settings = True
        self.settings.beginGroup("collage")
        values = {key: self.settings.value(key) for key in self.settings.childKeys()}
        self.settings.endGroup()
        if values:
            self.collage_panel.restore_settings_values(values)
        self._restoring_collage_settings = False

    def choose_collage_files(self) -> None:
        dialog = self.make_file_dialog("选择拼图照片（可多选）", Path.home())
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilter("图片 (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
        if dialog.exec() == QDialog.Accepted:
            self.collage_selector.add_files(dialog.selectedFiles())
            self.save_collage_photo_paths()

    def clear_collage_photos(self) -> None:
        self.collage_preview_request_id += 1
        self.collage_selector.clear()
        self.collage_preview_label.clear()
        self.collage_preview_label.setText("请选择参与拼图的照片")
        self.collage_status_label.setText("拼图: -")
        self.settings.remove("collage_photo_paths")

    def restore_collage_photos(self) -> None:
        if not hasattr(self, "collage_selector"):
            return
        raw_paths = self.settings.value("collage_photo_paths", [])
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        existing_paths = [
            str(path)
            for path in raw_paths
            if Path(str(path)).is_file() and Path(str(path)).suffix.lower() in IMAGE_EXTENSIONS
        ]
        if existing_paths:
            self.collage_selector.add_files(existing_paths)

    def save_collage_photo_paths(self) -> None:
        if not hasattr(self, "collage_selector"):
            return
        self.settings.setValue("collage_photo_paths", [str(path) for path in self.collage_selector.all_photos()])

    def restore_collage_groups(self) -> None:
        text = str(self.settings.value("collage_groups_json", ""))
        self.collage_group_store = CollageGroupStore.from_json(text, IMAGE_EXTENSIONS)
        self.save_collage_groups()
        self.refresh_collage_group_list()

    def save_collage_groups(self) -> None:
        self.settings.setValue("collage_groups_json", self.collage_group_store.to_json())

    def mark_collage_dirty(self) -> None:
        if self._loading_collage_group or self._restoring_collage_settings:
            return
        self.collage_dirty = True
        self.update_collage_group_dirty_marker()

    def current_collage_paths(self) -> list[Path]:
        return self.collage_selector.selected_photos()

    def current_collage_group(self) -> CollageGroup | None:
        if not self.current_collage_group_id:
            return None
        return self.collage_group_store.by_id(self.current_collage_group_id)

    def add_collage_group(self) -> None:
        paths = self.current_collage_paths()
        if not paths:
            QMessageBox.information(self, "没有照片", "请先选择参与拼图的照片。")
            return
        group = CollageGroup.create(
            self.collage_group_store.next_name(),
            paths,
            self.collage_panel.current_layout(),
            self.collage_panel.options(),
            self.collage_panel.quality_spin.value(),
        )
        self.collage_group_store.groups.append(group)
        self.current_collage_group_id = group.id
        self.collage_dirty = False
        self.save_collage_groups()
        self.refresh_collage_group_list(select_id=group.id)

    def update_current_collage_group(self) -> None:
        group = self.current_collage_group()
        if group is None:
            self.add_collage_group()
            return
        paths = self.current_collage_paths()
        if not paths:
            QMessageBox.information(self, "没有照片", "请先选择参与拼图的照片。")
            return
        group.update_from_editor(
            paths,
            self.collage_panel.current_layout(),
            self.collage_panel.options(),
            self.collage_panel.quality_spin.value(),
        )
        self.collage_dirty = False
        self.save_collage_groups()
        self.refresh_collage_group_list(select_id=group.id)

    def rename_current_collage_group(self) -> None:
        group = self.current_collage_group()
        if group is None:
            QMessageBox.information(self, "没有拼图组", "请先选择一个拼图组。")
            return
        name, ok = QInputDialog.getText(self, "重命名拼图组", "组名：", text=group.name)
        if not ok or not name.strip():
            return
        group.name = name.strip()
        group.updated_at = timestamp()
        self.save_collage_groups()
        self.refresh_collage_group_list(select_id=group.id)

    def copy_current_collage_group(self) -> None:
        group = self.current_collage_group()
        if group is None:
            QMessageBox.information(self, "没有拼图组", "请先选择一个拼图组。")
            return
        new_group = group.copy(self.collage_group_store.duplicate_name(group.name))
        self.collage_group_store.groups.append(new_group)
        self.current_collage_group_id = new_group.id
        self.collage_dirty = False
        self.save_collage_groups()
        self.refresh_collage_group_list(select_id=new_group.id)
        self.apply_collage_group(new_group)

    def delete_current_collage_group(self) -> None:
        group = self.current_collage_group()
        if group is None:
            QMessageBox.information(self, "没有拼图组", "请先选择一个拼图组。")
            return
        reply = QMessageBox.question(
            self,
            "删除拼图组",
            f"确定删除 \"{group.name}\" 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.collage_group_store.remove(group.id)
        self.current_collage_group_id = ""
        self.collage_dirty = False
        self.save_collage_groups()
        self.refresh_collage_group_list()

    def on_collage_group_selected(self, current: QListWidgetItem | None) -> None:
        if self._loading_collage_group or current is None:
            return
        group_id = str(current.data(Qt.UserRole) or "")
        if not group_id or group_id == self.current_collage_group_id:
            return
        if not self.confirm_collage_group_switch():
            self.select_collage_group_item(self.current_collage_group_id)
            return
        group = self.collage_group_store.by_id(group_id)
        if group is not None:
            self.apply_collage_group(group)

    def confirm_collage_group_switch(self) -> bool:
        if not self.collage_dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("保存当前修改？")
        box.setText("当前拼图组有未保存修改，切换前是否保存？")
        save_button = box.addButton("保存并切换", QMessageBox.AcceptRole)
        discard_button = box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_button = box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_button:
            return False
        if clicked == save_button:
            self.update_current_collage_group()
        elif clicked == discard_button:
            self.collage_dirty = False
        return True

    def apply_collage_group(self, group: CollageGroup) -> None:
        valid_paths = group.valid_paths(IMAGE_EXTENSIONS)
        if not valid_paths:
            self.collage_group_store.remove(group.id)
            self.save_collage_groups()
            self.refresh_collage_group_list()
            return
        self._loading_collage_group = True
        self.collage_selector.add_files([str(path) for path in valid_paths])
        self.collage_selector.set_selected_photos(valid_paths)
        self.collage_panel.apply_group_values(group.layout_name, group.options)
        self.collage_panel.set_quality(group.jpg_quality)
        self.current_collage_group_id = group.id
        self.collage_dirty = False
        self._loading_collage_group = False
        self.schedule_collage_preview()

    def refresh_collage_group_list(self, select_id: str = "") -> None:
        if not hasattr(self, "collage_group_list"):
            return
        current_id = select_id or self.current_collage_group_id
        self.collage_group_list.blockSignals(True)
        self.collage_group_list.clear()
        for group in self.collage_group_store.groups:
            item = QListWidgetItem(self.collage_group_item_text(group))
            item.setData(Qt.UserRole, group.id)
            item.setToolTip("\n".join(group.photo_paths))
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            thumb = self.collage_group_thumbnail(group)
            if thumb is not None:
                item.setIcon(thumb)
            self.collage_group_list.addItem(item)
            if group.id == current_id:
                self.collage_group_list.setCurrentItem(item)
        self.collage_group_list.blockSignals(False)

    def collage_group_item_text(self, group: CollageGroup) -> str:
        prefix = "* " if group.id == self.current_collage_group_id and self.collage_dirty else ""
        return f"{prefix}{group.name}\n{len(group.photo_paths)} 张 · {group.layout_name}"

    def update_collage_group_dirty_marker(self) -> None:
        if not hasattr(self, "collage_group_list") or not self.current_collage_group_id:
            return
        for index in range(self.collage_group_list.count()):
            item = self.collage_group_list.item(index)
            group_id = str(item.data(Qt.UserRole) or "")
            group = self.collage_group_store.by_id(group_id)
            if group is not None:
                item.setText(self.collage_group_item_text(group))

    def on_collage_group_rows_moved(self) -> None:
        if not hasattr(self, "collage_group_list"):
            return
        ordered_ids = [
            str(self.collage_group_list.item(index).data(Qt.UserRole) or "")
            for index in range(self.collage_group_list.count())
        ]
        self.collage_group_store.reorder(ordered_ids)
        self.save_collage_groups()

    def select_collage_group_item(self, group_id: str) -> None:
        self.collage_group_list.blockSignals(True)
        for index in range(self.collage_group_list.count()):
            item = self.collage_group_list.item(index)
            if str(item.data(Qt.UserRole) or "") == group_id:
                self.collage_group_list.setCurrentItem(item)
                break
        self.collage_group_list.blockSignals(False)

    def collage_group_thumbnail(self, group: CollageGroup):
        try:
            image = self.collage_engine.create_collage_from_paths(
                [Path(path) for path in group.photo_paths],
                layout_by_name(group.layout_name),
                group.options,
                max_source_edge=260,
            )
            image.thumbnail((96, 64), Image.Resampling.LANCZOS)
            return QIcon(QPixmap.fromImage(ImageQt(image.convert("RGBA"))))
        except Exception:
            return None

    def schedule_collage_preview(self) -> None:
        if hasattr(self, "collage_preview_timer"):
            self.collage_preview_timer.start(160)

    def update_collage_preview(self) -> None:
        if not hasattr(self, "collage_selector"):
            return
        paths = self.collage_selector.selected_photos()
        if not paths:
            self.collage_preview_label.clear()
            self.collage_preview_label.setText("请选择参与拼图的照片")
            self.collage_status_label.setText("拼图: -")
            return
        layout = self.collage_panel.current_layout()
        options = self.collage_panel.options()
        target_edge = max(
            640,
            min(
                PREVIEW_MAX_SOURCE_EDGE,
                int(max(self.collage_preview_label.width(), self.collage_preview_label.height()) * 1.5),
            ),
        )
        self.collage_preview_request_id += 1
        request_id = self.collage_preview_request_id
        self.collage_status_label.setText(f"拼图: {layout.name}    正在生成预览...")
        thread = QThread(self)
        worker = CollagePreviewWorker(request_id, paths, layout, options, target_edge)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.on_collage_preview_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self.clear_collage_preview_job(t, w))
        self.collage_preview_jobs.append((thread, worker))
        thread.start()

    def on_collage_preview_finished(
        self,
        request_id: int,
        rendered,
        error: str,
        layout_name: str,
        selected_count: int,
        cell_count: int,
        original_size: tuple[int, int],
    ) -> None:
        if request_id != self.collage_preview_request_id:
            return
        if error:
            self.collage_preview_label.setText(f"预览失败: {error}")
            self.collage_status_label.setText("拼图: 预览失败")
            return
        preview = rendered.copy()
        preview.thumbnail(
            (self.collage_preview_label.width() - 24, self.collage_preview_label.height() - 24),
            resample=Image.Resampling.LANCZOS,
        )
        pixmap = QPixmap.fromImage(ImageQt(preview.convert("RGBA")))
        self.collage_preview_label.setPixmap(pixmap)
        extra = ""
        if selected_count > cell_count:
            extra = f"    已选择 {selected_count} 张，仅使用前 {cell_count} 张"
        elif selected_count < cell_count:
            extra = f"    已选择 {selected_count} 张，空位显示背景色"
        self.collage_status_label.setText(
            f"拼图: {layout_name}    预览: {preview.width} x {preview.height}    导出: {original_size[0]} x {original_size[1]}{extra}"
        )

    def clear_collage_preview_job(self, thread: QThread, worker: CollagePreviewWorker) -> None:
        self.collage_preview_jobs = [job for job in self.collage_preview_jobs if job != (thread, worker)]

    def export_collage(self) -> None:
        paths = self.collage_selector.selected_photos()
        if not paths:
            QMessageBox.information(self, "没有照片", "请先选择参与拼图的照片。")
            return
        output = self.choose_export_file(self.last_export_dir() / "collage.jpg")
        if not output:
            return
        self.save_last_export_dir(output.parent)
        try:
            rendered = self.collage_engine.create_collage_from_paths(
                paths,
                self.collage_panel.current_layout(),
                self.collage_panel.options(),
            )
            save_rendered(rendered, output, self.collage_panel.quality_spin.value())
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "已导出", "拼图导出完成。")

    def export_collage_groups(self) -> None:
        groups: list[CollageGroup] = []
        for group in self.collage_group_store.groups:
            valid_paths = group.valid_paths(IMAGE_EXTENSIONS)
            if valid_paths:
                group.photo_paths = [str(path) for path in valid_paths]
                groups.append(group)
        self.collage_group_store.groups = groups
        self.save_collage_groups()
        self.refresh_collage_group_list()
        if not groups:
            QMessageBox.information(self, "没有拼图组", "请先暂存至少一个拼图组。")
            return
        if self.collage_batch_thread is not None:
            QMessageBox.information(self, "正在导出", "当前已有拼图组导出任务正在运行。")
            return
        directory = self.choose_directory("选择拼图组批量导出目录", self.last_export_dir())
        if not directory:
            return
        self.save_last_export_dir(directory)
        suffix = str(self.collage_export_format_combo.currentData() or ".jpg")
        used_names: set[str] = set()
        jobs = [
            (group, directory / safe_filename(group.name, used_names, suffix), group.jpg_quality)
            for group in groups
        ]
        self.start_collage_group_export(jobs)

    def start_collage_group_export(self, jobs: list[tuple[CollageGroup, Path, int]]) -> None:
        thread = QThread(self)
        worker = CollageBatchExportWorker(jobs)
        dialog = ExportProgressDialog(len(jobs), self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.update_progress)
        worker.finished.connect(self.on_collage_group_export_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.clear_collage_group_export_task)
        dialog.cancelRequested.connect(worker.cancel)

        self.collage_batch_thread = thread
        self.collage_batch_worker = worker
        self.collage_batch_dialog = dialog
        dialog.show()
        thread.start()

    def on_collage_group_export_finished(self, completed: int, total: int, canceled: bool, message: str) -> None:
        if self.collage_batch_dialog:
            self.collage_batch_dialog.accept()
        if canceled:
            QMessageBox.information(self, "导出已取消", f"已导出 {completed} / {total} 个拼图组。")
        elif message:
            QMessageBox.warning(self, "导出完成但有错误", f"已导出 {completed} / {total} 个拼图组。\n\n{message}")
        else:
            QMessageBox.information(self, "批量导出完成", f"已导出 {completed} 个拼图组。")

    def clear_collage_group_export_task(self) -> None:
        self.collage_batch_thread = None
        self.collage_batch_worker = None
        self.collage_batch_dialog = None

    def apply_window_style(self) -> None:
        dark = self.current_theme_is_dark()
        bg = "#202124" if dark else "#f7f8fa"
        panel = "#2a2b2f" if dark else "#ffffff"
        border = "#3a3b40" if dark else "#e5e7eb"
        text = "#f3f4f6" if dark else "#111827"
        text_muted = "#c7cbd1" if dark else "#6b7280"
        preview_bg = "#15161a" if dark else "#eef1f5"
        self.setStyleSheet(
            f"""
            QWidget#watermarkPage {{
                background-color: {bg};
            }}
            QWidget#collagePage {{
                background-color: {bg};
            }}
            QWidget#settingsPanel,
            OpacityAniStackedWidget#settingsStack,
            QScrollArea#settingsPage,
            QWidget#settingsViewport,
            QWidget#settingsContent {{
                background-color: {bg};
            }}
            QDialog {{
                background-color: {bg};
            }}
            QWidget#settingSection {{
                background-color: {panel};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel {{
                color: {text};
            }}
            QLabel#mutedLabel {{
                color: {text_muted};
            }}
            QLabel#previewLabel {{
                background-color: {preview_bg};
                color: {text};
                border-radius: 8px;
                font-size: 15px;
            }}
            QSplitter::handle {{
                background-color: {border};
                width: 2px;
            }}
            """
        )

    def connect_preview_signal(self, widget) -> None:
        if isinstance(widget, ExifFieldList):
            widget.valueChanged.connect(lambda *_: self.schedule_preview())
        elif isinstance(widget, (NumericSlider, QSlider, QSpinBox)):
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

    def connect_exif_signals(self) -> None:
        widgets = [
            self.subtitle_input,
            self.exif_position_combo,
            self.exif_scale_slider,
            self.exif_opacity_slider,
            self.exif_line_spacing_slider,
            self.exif_second_line_indent_slider,
            self.exif_offset_x_slider,
            self.exif_offset_y_slider,
            self.exif_field_list,
        ]
        for widget in widgets:
            self.connect_preview_signal(widget)
        self.exif_field_list.valueChanged.connect(self.update_exif_summary)
        self.subtitle_input.textChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_position_combo.currentIndexChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_scale_slider.valueChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_opacity_slider.valueChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_line_spacing_slider.valueChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_second_line_indent_slider.valueChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_offset_x_slider.valueChanged.connect(lambda *_: self.update_exif_summary())
        self.exif_offset_y_slider.valueChanged.connect(lambda *_: self.update_exif_summary())

    def connect_save_signal(self, widget) -> None:
        if isinstance(widget, ExifFieldList):
            widget.valueChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, (NumericSlider, QSlider, QSpinBox)):
            widget.valueChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda *_: self.save_render_settings())
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(lambda *_: self.save_render_settings())

    def update_exif_summary(self) -> None:
        pass

    def render_setting_widgets(self) -> dict[str, object]:
        return {
            "template": self.template_combo,
            "blur_style": self.blur_style_combo,
            "title_position": self.position_combo,
            "title_text": self.title_input,
            "title_font": self.title_font_combo,
            "title_opacity": self.title_opacity_slider,
            "subtitle_text": self.subtitle_input,
            "exif_fields": self.exif_field_list,
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
            "exif_line_spacing": self.exif_line_spacing_slider,
            "exif_second_line_indent": self.exif_second_line_indent_slider,
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
        self.settings.beginGroup(self.render_settings_group(self.current_ratio_key))
        for key, widget in self.render_setting_widgets().items():
            if isinstance(widget, NumericSlider):
                self.settings.setValue(key, widget.value())
            elif isinstance(widget, QSpinBox):
                self.settings.setValue(key, widget.value())
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                self.settings.setValue(key, data.value if hasattr(data, "value") else data or "")
            elif isinstance(widget, ExifFieldList):
                self.settings.setValue(key, widget.serialized_value())
            elif isinstance(widget, QLineEdit):
                self.settings.setValue(key, widget.text())
            elif isinstance(widget, QCheckBox):
                self.settings.setValue(key, widget.isChecked())
        self.settings.endGroup()

    def restore_render_settings(self, ratio_key: str | None = None) -> None:
        ratio_key = ratio_key or "default"
        self._restoring_settings = True
        values = self.render_settings_values(ratio_key)
        for key, widget in self.render_setting_widgets().items():
            if key not in values:
                continue
            value = values[key]
            if isinstance(widget, NumericSlider):
                self.set_numeric_slider_value(widget, value)
            elif isinstance(widget, QSpinBox):
                self.set_spinbox_value(widget, value)
            elif isinstance(widget, QComboBox):
                self.set_combo_value(widget, value)
            elif isinstance(widget, ExifFieldList):
                widget.restore_serialized_value(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(self.settings_bool(value))
        self._restoring_settings = False
        self.current_ratio_key = ratio_key
        self.update_exif_summary()

    def render_settings_group(self, ratio_key: str) -> str:
        return "render" if ratio_key == "default" else f"render/{ratio_key}"

    def render_settings_values(self, ratio_key: str) -> dict[str, object]:
        values = self.read_render_settings_group("render")
        if ratio_key != "default":
            values.update(self.read_render_settings_group(self.render_settings_group(ratio_key)))
        return values

    def read_render_settings_group(self, group: str) -> dict[str, object]:
        values: dict[str, object] = {}
        self.settings.beginGroup(group)
        for key in self.settings.childKeys():
            values[key] = self.settings.value(key)
        self.settings.endGroup()
        return values

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

    def on_template_changed(self) -> None:
        enabled = self.template_combo.currentData() == TemplateKind.BLUR_FRAME
        self.blur_style_combo.setEnabled(enabled)
        self.blur_slider.setEnabled(enabled)
        self.refresh_presets()
        self.update_exif_summary()

    def refresh_presets(self) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        template = self.template_combo.currentData()
        if template and template != TemplateKind.NONE:
            for preset in self.preset_manager.presets_for(template):
                self.preset_combo.addItem(preset.name, userData=preset)
        self.preset_combo.blockSignals(False)
        has_presets = self.preset_combo.count() > 0
        self.preset_combo.setVisible(has_presets)
        self.save_preset_button.setVisible(has_presets)
        self.delete_preset_button.setVisible(has_presets)
        if has_presets:
            self.update_delete_button_state()

    def on_preset_selected(self, index: int) -> None:
        preset = self.preset_combo.currentData()
        if preset is None:
            return
        self._restoring_settings = True
        self._apply_preset_to_ui(preset)
        self._restoring_settings = False
        self.update_delete_button_state()
        self.schedule_preview()

    def _apply_preset_to_ui(self, preset: Preset) -> None:
        mapping = {
            "title_position": (self.position_combo, WatermarkPosition),
            "title_offset_x_percent": (self.title_offset_x_slider, 100),
            "title_offset_y_percent": (self.title_offset_y_slider, 100),
            "title_opacity": (self.title_opacity_slider, 100),
            "title_font_name": (self.title_font_combo, "combo_str"),
            "text_scale": (self.text_scale_slider, 100),
            "exif_position": (self.exif_position_combo, WatermarkPosition),
            "exif_scale": (self.exif_scale_slider, 100),
            "exif_opacity": (self.exif_opacity_slider, 100),
            "exif_line_spacing": (self.exif_line_spacing_slider, 100),
            "exif_second_line_indent_percent": (self.exif_second_line_indent_slider, 100),
            "exif_offset_x_percent": (self.exif_offset_x_slider, 100),
            "exif_offset_y_percent": (self.exif_offset_y_slider, 100),
            "logo_position": (self.logo_position_combo, WatermarkPosition),
            "logo_scale": (self.logo_scale_slider, 100),
            "logo_offset_x_percent": (self.logo_offset_x_slider, 100),
            "logo_offset_y_percent": (self.logo_offset_y_slider, 100),
            "opacity": (self.opacity_slider, 100),
            "border_percent": (self.border_slider, 100),
            "bottom_percent": (self.bottom_slider, 100),
            "main_image_percent": (self.main_image_slider, 100),
            "corner_radius_percent": (self.corner_radius_slider, 100),
            "shadow_percent": (self.shadow_slider, 100),
            "blur_percent": (self.blur_slider, 100),
            "blur_style": (self.blur_style_combo, BlurStyle),
            "background_color": (self.background_color_input, "text"),
        }
        data = preset.to_dict()
        for key, (widget, scale_or_type) in mapping.items():
            value = data.get(key)
            if value is None:
                continue
            if scale_or_type is WatermarkPosition or scale_or_type is BlurStyle:
                self.set_combo_value(widget, value)
            elif scale_or_type == "combo_str":
                self.set_combo_value(widget, value)
            elif scale_or_type == "text":
                widget.setText(str(value))
            else:
                widget.setValue(float(value) * scale_or_type)

    def save_current_preset(self) -> None:
        template = self.template_combo.currentData()
        if not template or template == TemplateKind.NONE:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "保存预设", "预设名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        if self.preset_manager.is_system_preset(template, name):
            QMessageBox.warning(self, "名称冲突", "系统预设名称不可用，请换一个名称。")
            return
        defaults = RenderOptions()
        current = self.collect_options()
        preset = Preset.from_render_options(name, template, current, defaults)
        self.preset_manager.save_user_preset(preset)
        self.refresh_presets()
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemText(i) == name:
                self.preset_combo.setCurrentIndex(i)
                break

    def delete_current_preset(self) -> None:
        preset = self.preset_combo.currentData()
        if preset is None:
            return
        if preset.is_system:
            QMessageBox.information(self, "无法删除", "系统预设不可删除。")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除预设 \"{preset.name}\" 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.preset_manager.delete_user_preset(preset.template, preset.name)
        self.refresh_presets()

    def update_delete_button_state(self) -> None:
        preset = self.preset_combo.currentData()
        self.delete_preset_button.setEnabled(preset is not None and not preset.is_system)

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
        self.watermark_combo.addItem("无", userData="")
        self.watermark_dir_label.setText(str(self.watermark_dir))
        if self.watermark_dir.exists():
            for path in sorted(self.watermark_dir.rglob("*.png")):
                if path.name.startswith("ChatGPT Image"):
                    continue
                try:
                    label = str(path.relative_to(self.watermark_dir))
                except ValueError:
                    label = path.name
                self.watermark_combo.addItem(label, userData=str(path))

    def restore_watermark_selection(self) -> None:
        value = self.render_settings_values(self.current_ratio_key).get("png_watermark_path", "")
        self.set_combo_value(self.watermark_combo, value)

    def choose_watermark_dir(self) -> None:
        directory = self.choose_directory("选择水印素材目录", self.watermark_dir)
        if not directory:
            return
        self.watermark_dir = directory
        self.settings.setValue("watermark_dir", str(self.watermark_dir))
        self.load_watermarks()
        self.restore_watermark_selection()
        self.schedule_preview()

    def choose_files(self) -> None:
        dialog = self.make_file_dialog("选择照片（可多选）", Path.home())
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilter("图片 (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
        if dialog.exec() == QDialog.Accepted:
            self.add_files(dialog.selectedFiles())

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

    def add_files(self, files: list[str]) -> None:
        added = False
        first_added: QTreeWidgetItem | None = None
        for raw in files:
            path = Path(raw)
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path not in self.photo_paths:
                self.photo_paths.append(path)
                ratio_key, ratio_label = self.photo_ratio(path)
                group = self.ratio_groups.get(ratio_key)
                if group is None:
                    group = QTreeWidgetItem([ratio_label])
                    group.setData(0, Qt.UserRole, "")
                    group.setData(0, Qt.UserRole + 1, ratio_key)
                    self.photo_list.addTopLevelItem(group)
                    self.ratio_groups[ratio_key] = group
                item = QTreeWidgetItem([path.name])
                item.setData(0, Qt.UserRole, str(path))
                item.setData(0, Qt.UserRole + 1, ratio_key)
                group.addChild(item)
                group.setText(0, f"{ratio_label} ({group.childCount()})")
                group.setExpanded(True)
                first_added = first_added or item
                added = True
        self.update_photo_count()
        if added:
            self.save_photo_paths()
        if added and self.current_photo() is None and first_added is not None:
            self.photo_list.setCurrentItem(first_added)

    def clear_photos(self) -> None:
        self.photo_paths.clear()
        self.photo_list.clear()
        self.ratio_groups.clear()
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

    def on_photo_changed(self, current: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        raw_path = current.data(0, Qt.UserRole)
        if not raw_path:
            if current.childCount() > 0:
                self.photo_list.setCurrentItem(current.child(0))
            return
        self.save_render_settings()
        ratio_key = str(current.data(0, Qt.UserRole + 1) or "default")
        if ratio_key != self.current_ratio_key:
            self.restore_render_settings(ratio_key)
        path = Path(str(raw_path))
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
        raw_path = item.data(0, Qt.UserRole)
        return Path(raw_path) if raw_path else None

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
            exif_line_spacing=self.exif_line_spacing_slider.value() / 100,
            exif_second_line_indent_percent=self.exif_second_line_indent_slider.value() / 100,
            exif_offset_x_percent=self.exif_offset_x_slider.value() / 100,
            exif_offset_y_percent=self.exif_offset_y_slider.value() / 100,
            show_brand_logo=self.logo_group.isChecked(),
            logo_position=self.logo_position_combo.currentData(),
            logo_scale=self.logo_scale_slider.value() / 100,
            logo_offset_x_percent=self.logo_offset_x_slider.value() / 100,
            logo_offset_y_percent=self.logo_offset_y_slider.value() / 100,
            detail_template=self.exif_field_list.template_text(),
            text_scale=self.text_scale_slider.value() / 100,
            opacity=self.opacity_slider.value() / 100,
            border_percent=self.border_slider.value() / 100,
            bottom_percent=self.bottom_slider.value() / 100,
            main_image_percent=self.main_image_slider.value() / 100,
            corner_radius_percent=self.corner_radius_slider.value() / 100,
            shadow_percent=self.shadow_slider.value() / 100,
            blur_percent=self.blur_slider.value() / 100,
            blur_style=self.blur_style_combo.currentData(),
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
        if self.export_thread is not None:
            QMessageBox.information(self, "正在导出", "当前已有导出任务正在运行。")
            return
        export_dir = self.last_export_dir()
        default = export_dir / f"{path.stem}_watermarked.jpg"
        output = self.choose_export_file(default)
        if not output:
            return
        self.save_last_export_dir(output.parent)
        self.start_export([(path, output, self.options_for_photo(path))])

    def export_all(self) -> None:
        if not self.photo_paths:
            QMessageBox.information(self, "没有照片", "请先导入照片。")
            return
        if self.export_thread is not None:
            QMessageBox.information(self, "正在导出", "当前已有导出任务正在运行。")
            return
        directory = self.choose_directory("选择批量导出目录", self.last_export_dir())
        if not directory:
            return
        output_dir = directory
        self.save_last_export_dir(output_dir)
        jobs = [(path, output_dir / f"{path.stem}_watermarked.jpg", self.options_for_photo(path)) for path in self.photo_paths]
        self.start_export(jobs)

    def options_for_photo(self, path: Path) -> RenderOptions:
        self.save_render_settings()
        current_ratio_key = self.current_ratio_key
        ratio_key, _ = self.photo_ratio(path)
        if ratio_key == current_ratio_key:
            return self.collect_options()
        self.restore_render_settings(ratio_key)
        options = self.collect_options()
        self.restore_render_settings(current_ratio_key)
        return options

    def make_file_dialog(self, title: str, directory: Path) -> QFileDialog:
        dialog = QFileDialog(self, title, str(directory))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setLabelText(QFileDialog.LookIn, "位置")
        dialog.setLabelText(QFileDialog.FileName, "文件名")
        dialog.setLabelText(QFileDialog.FileType, "文件类型")
        dialog.setLabelText(QFileDialog.Accept, "确定")
        dialog.setLabelText(QFileDialog.Reject, "取消")
        return dialog

    def choose_directory(self, title: str, directory: Path) -> Path | None:
        dialog = self.make_file_dialog(title, directory)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec() != QDialog.Accepted:
            return None
        selected = dialog.selectedFiles()
        return Path(selected[0]) if selected else None

    def choose_export_file(self, default_path: Path) -> Path | None:
        dialog = self.make_file_dialog("导出照片", default_path.parent)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setNameFilters(["JPEG (*.jpg)", "PNG (*.png)"])
        dialog.selectFile(default_path.name)
        if dialog.exec() != QDialog.Accepted:
            return None
        selected = dialog.selectedFiles()
        if not selected:
            return None
        output = Path(selected[0])
        if not output.suffix:
            output = output.with_suffix(".jpg")
        return output

    def last_export_dir(self) -> Path:
        path = Path(self.settings.value("last_export_dir", str(Path.home())))
        return path if path.exists() else Path.home()

    def save_last_export_dir(self, directory: Path) -> None:
        self.settings.setValue("last_export_dir", str(directory))

    def start_export(self, jobs: list[tuple[Path, Path, RenderOptions]]) -> None:
        thread = QThread(self)
        worker = ExportWorker(jobs)
        dialog = ExportProgressDialog(len(jobs), self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.update_progress)
        worker.finished.connect(self.on_export_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.clear_export_task)
        dialog.cancelRequested.connect(worker.cancel)

        self.export_thread = thread
        self.export_worker = worker
        self.export_dialog = dialog
        dialog.show()
        thread.start()

    def on_export_finished(self, completed: int, total: int, canceled: bool, message: str) -> None:
        if self.export_dialog:
            self.export_dialog.accept()
        if canceled:
            QMessageBox.information(self, "导出已取消", f"已导出 {completed} / {total} 张照片。")
        elif message:
            QMessageBox.warning(self, "导出完成但有错误", f"已导出 {completed} / {total} 张照片。\n\n{message}")
        elif total == 1:
            QMessageBox.information(self, "已导出", "照片导出完成。")
        else:
            QMessageBox.information(self, "批量导出完成", f"已导出 {completed} 张照片。")

    def clear_export_task(self) -> None:
        self.export_thread = None
        self.export_worker = None
        self.export_dialog = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if sys.platform == "darwin":
            self.titleBar.move(0, 0)
            self.titleBar.resize(self.width(), self.titleBar.height())
        self.schedule_preview()
        self.schedule_collage_preview()

    def systemTitleBarRect(self, size: QSize) -> QRect:
        if sys.platform == "darwin":
            return QRect(0, 0 if self.isFullScreen() else 8, 75, size.height())
        return super().systemTitleBarRect(size)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
