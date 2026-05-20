from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox as QComboBox, LineEdit as QLineEdit, ListWidget as QListWidget, PrimaryPushButton, PushButton as QPushButton, SpinBox as QSpinBox

from watermark_app.core.i18n import tr
from watermark_app.core.social_export import SOCIAL_PRESETS, SocialExportOptions, export_social_image


class SocialExportPage(QWidget):
    def __init__(self, image_extensions: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("socialExportPage")
        self.image_extensions = image_extensions
        self.paths: list[Path] = []

        self.import_button = QPushButton()
        self.import_button.clicked.connect(self.choose_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self.clear)
        self.export_button = PrimaryPushButton()
        self.export_button.clicked.connect(self.export_all)

        self.list_widget = QListWidget()
        self.preset_combo = QComboBox()
        for preset in SOCIAL_PRESETS:
            self.preset_combo.addItem(f"{preset.name} ({preset.width}x{preset.height})", userData=preset)
        self.fit_combo = QComboBox()
        self.background_input = QLineEdit()
        self.background_input.setText("#ffffff")
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(92)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.clear_button)
        row.addWidget(self.export_button)
        layout.addLayout(row)
        body = QHBoxLayout()
        body.addWidget(self.list_widget, 2)
        settings = QVBoxLayout()
        settings.addWidget(self.preset_combo)
        settings.addWidget(self.fit_combo)
        settings.addWidget(self.background_input)
        settings.addWidget(self.quality_spin)
        settings.addStretch(1)
        body.addLayout(settings, 1)
        layout.addLayout(body, 1)
        self.refresh_texts()

    def refresh_texts(self) -> None:
        fit_mode = self.fit_combo.currentData() or "contain"
        self.import_button.setText(tr("common.import_photos"))
        self.clear_button.setText(tr("common.clear"))
        self.export_button.setText(tr("social.export_all"))
        self.fit_combo.blockSignals(True)
        self.fit_combo.clear()
        self.fit_combo.addItem(tr("social.contain"), userData="contain")
        self.fit_combo.addItem(tr("social.cover"), userData="cover")
        self.set_combo_value(self.fit_combo, str(fit_mode))
        self.fit_combo.blockSignals(False)

    def choose_files(self) -> None:
        dialog = QFileDialog(self, "选择社交媒体导出照片", str(Path.home()))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilter("图片 (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
        if dialog.exec():
            for raw in dialog.selectedFiles():
                path = Path(raw)
                if path.is_file() and path.suffix.lower() in self.image_extensions and path not in self.paths:
                    self.paths.append(path)
                    self.list_widget.addItem(QListWidgetItem(path.name))

    def clear(self) -> None:
        self.paths.clear()
        self.list_widget.clear()

    def options(self) -> SocialExportOptions:
        return SocialExportOptions(
            preset=self.preset_combo.currentData(),
            background_color=self.background_input.text(),
            fit_mode=self.fit_combo.currentData() or "contain",
            quality=self.quality_spin.value(),
        )

    def export_all(self) -> None:
        if not self.paths:
            QMessageBox.information(self, tr("common.no_photos"), tr("common.choose_first"))
            return
        dialog = QFileDialog(self, tr("social.choose_dir"), str(Path.home()))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if not dialog.exec():
            return
        directory = Path(dialog.selectedFiles()[0])
        options = self.options()
        for path in self.paths:
            output = directory / f"{path.stem}_{options.preset.name.replace(' ', '_').replace('/', '_')}.jpg"
            export_social_image(path, output, options)
        QMessageBox.information(self, tr("common.done"), tr("social.done_count", count=len(self.paths)))

    def set_combo_value(self, widget: QComboBox, value: str) -> None:
        for index in range(widget.count()):
            if widget.itemData(index) == value:
                widget.setCurrentIndex(index)
                return
