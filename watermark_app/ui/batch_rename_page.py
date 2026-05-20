from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import LineEdit as QLineEdit, ListWidget as QListWidget, PrimaryPushButton, PushButton as QPushButton, SpinBox as QSpinBox

from watermark_app.core.batch_rename import RenamePlanItem, apply_rename_plan, build_rename_plan
from watermark_app.core.i18n import tr


class BatchRenamePage(QWidget):
    def __init__(self, image_extensions: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchRenamePage")
        self.image_extensions = image_extensions
        self.paths: list[Path] = []
        self.plan: list[RenamePlanItem] = []

        self.import_button = QPushButton()
        self.import_button.clicked.connect(self.choose_files)
        self.preview_button = QPushButton()
        self.preview_button.clicked.connect(self.preview_plan)
        self.apply_button = PrimaryPushButton()
        self.apply_button.clicked.connect(self.apply_plan)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self.clear)

        self.template_input = QLineEdit()
        self.template_input.setText("{date}_{index}_{stem}")
        self.index_spin = QSpinBox()
        self.index_spin.setRange(1, 99999)
        self.index_spin.setValue(1)
        self.list_widget = QListWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.clear_button)
        row.addWidget(self.preview_button)
        row.addWidget(self.apply_button)
        layout.addLayout(row)
        settings = QHBoxLayout()
        settings.addWidget(self.template_input, 1)
        settings.addWidget(self.index_spin)
        layout.addLayout(settings)
        layout.addWidget(self.list_widget, 1)
        self.refresh_texts()

    def refresh_texts(self) -> None:
        self.import_button.setText(tr("common.import_photos"))
        self.clear_button.setText(tr("common.clear"))
        self.preview_button.setText(tr("rename.preview"))
        self.apply_button.setText(tr("rename.apply"))

    def choose_files(self) -> None:
        dialog = QFileDialog(self, "选择要重命名的照片", str(Path.home()))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilter("图片 (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
        if dialog.exec():
            for raw in dialog.selectedFiles():
                path = Path(raw)
                if path.is_file() and path.suffix.lower() in self.image_extensions and path not in self.paths:
                    self.paths.append(path)
            self.preview_plan()

    def clear(self) -> None:
        self.paths.clear()
        self.plan.clear()
        self.list_widget.clear()

    def preview_plan(self) -> None:
        self.plan = build_rename_plan(self.paths, self.template_input.text(), self.index_spin.value())
        self.list_widget.clear()
        for item in self.plan:
            self.list_widget.addItem(QListWidgetItem(f"{item.source.name}  ->  {item.target.name}"))

    def apply_plan(self) -> None:
        if not self.plan:
            self.preview_plan()
        if not self.plan:
            QMessageBox.information(self, tr("common.no_photos"), tr("common.choose_first"))
            return
        reply = QMessageBox.question(
            self,
            tr("rename.confirm"),
            tr("rename.confirm_text", count=len(self.plan)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        apply_rename_plan(self.plan)
        self.paths = [item.target for item in self.plan]
        self.preview_plan()
        QMessageBox.information(self, tr("common.done"), tr("rename.done"))
