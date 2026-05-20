from __future__ import annotations

from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel as QLabel, LineEdit as QLineEdit, ListWidget as QListWidget, PrimaryPushButton, PushButton as QPushButton, SpinBox as QSpinBox

from watermark_app.core.contact_sheet import ContactSheetOptions, create_contact_sheet
from watermark_app.core.i18n import tr
from watermark_app.core.renderer import save_rendered


class ContactSheetPage(QWidget):
    def __init__(self, image_extensions: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contactSheetPage")
        self.image_extensions = image_extensions
        self.paths: list[Path] = []
        self.rendered = None

        self.import_button = QPushButton()
        self.import_button.clicked.connect(self.choose_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self.clear)
        self.render_button = PrimaryPushButton()
        self.render_button.clicked.connect(self.render_sheet)
        self.export_button = QPushButton()
        self.export_button.clicked.connect(self.export_sheet)

        self.list_widget = QListWidget()
        self.preview_label = QLabel()
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(720, 520)
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 10)
        self.columns_spin.setValue(4)
        self.thumb_width_spin = QSpinBox()
        self.thumb_width_spin.setRange(120, 900)
        self.thumb_width_spin.setValue(360)
        self.thumb_height_spin = QSpinBox()
        self.thumb_height_spin.setRange(120, 900)
        self.thumb_height_spin.setValue(240)
        self.background_input = QLineEdit()
        self.background_input.setText("#ffffff")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.clear_button)
        row.addWidget(self.render_button)
        row.addWidget(self.export_button)
        layout.addLayout(row)
        body = QHBoxLayout()
        body.addWidget(self.list_widget, 1)
        body.addWidget(self.preview_label, 3)
        settings = QVBoxLayout()
        self.columns_label = QLabel()
        self.thumb_width_label = QLabel()
        self.thumb_height_label = QLabel()
        self.background_label = QLabel()
        settings.addWidget(self.columns_label)
        settings.addWidget(self.columns_spin)
        settings.addWidget(self.thumb_width_label)
        settings.addWidget(self.thumb_width_spin)
        settings.addWidget(self.thumb_height_label)
        settings.addWidget(self.thumb_height_spin)
        settings.addWidget(self.background_label)
        settings.addWidget(self.background_input)
        settings.addStretch(1)
        body.addLayout(settings, 1)
        layout.addLayout(body, 1)
        self.refresh_texts()

    def refresh_texts(self) -> None:
        self.import_button.setText(tr("common.import_photos"))
        self.clear_button.setText(tr("common.clear"))
        self.render_button.setText(tr("contact.render"))
        self.export_button.setText(tr("common.export"))
        self.columns_label.setText(tr("contact.columns"))
        self.thumb_width_label.setText(tr("contact.thumb_width"))
        self.thumb_height_label.setText(tr("contact.thumb_height"))
        self.background_label.setText(tr("contact.background"))
        if self.rendered is None:
            self.preview_label.setText(tr("contact.empty"))

    def choose_files(self) -> None:
        dialog = QFileDialog(self, "选择样片墙照片", str(Path.home()))
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
        self.rendered = None
        self.list_widget.clear()
        self.preview_label.clear()
        self.preview_label.setText(tr("contact.empty"))

    def options(self) -> ContactSheetOptions:
        return ContactSheetOptions(
            columns=self.columns_spin.value(),
            thumb_width=self.thumb_width_spin.value(),
            thumb_height=self.thumb_height_spin.value(),
            background_color=self.background_input.text(),
        )

    def render_sheet(self) -> None:
        if not self.paths:
            QMessageBox.information(self, tr("common.no_photos"), tr("common.choose_first"))
            return
        self.rendered = create_contact_sheet(self.paths, self.options())
        preview = self.rendered.copy()
        preview.thumbnail((self.preview_label.width() - 24, self.preview_label.height() - 24))
        self.preview_label.setPixmap(QPixmap.fromImage(ImageQt(preview.convert("RGBA"))))

    def export_sheet(self) -> None:
        if self.rendered is None:
            self.render_sheet()
        if self.rendered is None:
            return
        dialog = QFileDialog(self, tr("contact.export_title"), str(Path.home() / "contact_sheet.jpg"))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters(["JPEG (*.jpg)", "PNG (*.png)"])
        if not dialog.exec():
            return
        output = Path(dialog.selectedFiles()[0])
        if not output.suffix:
            output = output.with_suffix(".jpg")
        save_rendered(self.rendered, output)
        QMessageBox.information(self, tr("common.done"), tr("contact.export_done"))
