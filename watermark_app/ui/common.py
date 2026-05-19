from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CheckBox as QCheckBox,
    DoubleSpinBox as QDoubleSpinBox,
    PushButton as QPushButton,
    ScrollArea as QScrollArea,
    Slider as QSlider,
)


class ResettableSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation, default_value: int) -> None:
        super().__init__()
        self.setOrientation(orientation)
        self.default_value = default_value
        if hasattr(self, "handle"):
            self.handle.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "handle", None) and event.type() == event.Type.MouseButtonDblClick:
            self.setValue(self.default_value)
            return True
        return super().eventFilter(obj, event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.setValue(self.default_value)
        event.accept()

    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


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
        self.input.setSymbolVisible(False)
        self.input.setFixedWidth(92 if suffix else 84)
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
        self.setObjectName("settingSection")
        self.title = title
        self.header = QPushButton()
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setText(f"⌄ {title}")
        self.header.clicked.connect(self.on_header_clicked)
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.form.setContentsMargins(8, 4, 8, 8)
        self.form.setVerticalSpacing(6)
        self.form.setHorizontalSpacing(10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 8, 0)
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
        self.header.setText(f"{'⌄' if expanded else '›'} {self.title}")

    def is_enabled(self) -> bool:
        return True if self.enable_checkbox is None else self.enable_checkbox.isChecked()


def make_settings_page(*sections: QWidget) -> QWidget:
    page = QScrollArea()
    page.setObjectName("settingsPage")
    page.setWidgetResizable(True)
    page.viewport().setObjectName("settingsViewport")
    content = QWidget()
    content.setObjectName("settingsContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)
    for section in sections:
        layout.addWidget(section)
    layout.addStretch(1)
    page.setWidget(content)
    return page
