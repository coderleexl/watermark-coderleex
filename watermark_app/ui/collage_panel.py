from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import ComboBox as QComboBox, LineEdit as QLineEdit, SpinBox as QSpinBox

from watermark_app.core.collage import COLLAGE_LAYOUTS, CollageLayout, CollageOptions
from watermark_app.core.collage_groups import options_to_dict
from watermark_app.ui.common import CollapsibleSection, NumericSlider, make_settings_page


class CollagePanel(QWidget):
    optionsChanged = Signal()

    RATIOS = [
        ("自定义", None),
        ("1:1", (1, 1)),
        ("4:5", (4, 5)),
        ("3:2", (3, 2)),
        ("2:3", (2, 3)),
        ("16:9", (16, 9)),
        ("9:16", (9, 16)),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._syncing_size = False

        self.layout_combo = QComboBox()
        for layout in COLLAGE_LAYOUTS:
            self.layout_combo.addItem(layout.name, userData=layout)

        self.ratio_combo = QComboBox()
        for label, ratio in self.RATIOS:
            self.ratio_combo.addItem(label, userData=ratio)
        self.ratio_combo.setCurrentText("1:1")

        self.long_edge_spin = QSpinBox()
        self.long_edge_spin.setRange(400, 12000)
        self.long_edge_spin.setValue(2000)
        self.long_edge_spin.setSingleStep(100)
        self.long_edge_spin.setSymbolVisible(False)

        self.output_width_spin = QSpinBox()
        self.output_width_spin.setRange(400, 12000)
        self.output_width_spin.setValue(2000)
        self.output_width_spin.setSingleStep(100)
        self.output_width_spin.setSymbolVisible(False)

        self.output_height_spin = QSpinBox()
        self.output_height_spin.setRange(400, 12000)
        self.output_height_spin.setValue(2000)
        self.output_height_spin.setSingleStep(100)
        self.output_height_spin.setSymbolVisible(False)

        self.gap_slider = NumericSlider(0, 120, 12, decimals=0, step=1)
        self.corner_radius_slider = NumericSlider(0, 120, 0, decimals=0, step=1)
        self.background_color_input = QLineEdit()
        self.background_color_input.setText("#ffffff")
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(95)
        self.quality_spin.setSymbolVisible(False)

        layout_section = CollapsibleSection("布局 / 尺寸")
        layout_section.form.addRow("布局", self.layout_combo)
        layout_section.form.addRow("比例", self.ratio_combo)
        layout_section.form.addRow("长边", self.long_edge_spin)
        layout_section.form.addRow("宽度", self.output_width_spin)
        layout_section.form.addRow("高度", self.output_height_spin)

        style_section = CollapsibleSection("样式")
        style_section.form.addRow("间距", self.gap_slider)
        style_section.form.addRow("圆角", self.corner_radius_slider)
        style_section.form.addRow("背景色", self.background_color_input)

        export_section = CollapsibleSection("导出")
        export_section.form.addRow("JPG 质量", self.quality_spin)

        page = make_settings_page(layout_section, style_section, export_section)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page)

        self.ratio_combo.currentIndexChanged.connect(self.on_ratio_changed)
        self.long_edge_spin.valueChanged.connect(self.apply_ratio_size)
        self.output_width_spin.valueChanged.connect(self.on_manual_size_changed)
        self.output_height_spin.valueChanged.connect(self.on_manual_size_changed)
        for widget in [
            self.layout_combo,
            self.ratio_combo,
            self.long_edge_spin,
            self.output_width_spin,
            self.output_height_spin,
            self.gap_slider,
            self.corner_radius_slider,
            self.background_color_input,
            self.quality_spin,
        ]:
            self.connect_options_signal(widget)

    def connect_options_signal(self, widget) -> None:
        if isinstance(widget, NumericSlider):
            widget.valueChanged.connect(lambda *_: self.optionsChanged.emit())
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(lambda *_: self.optionsChanged.emit())
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda *_: self.optionsChanged.emit())
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda *_: self.optionsChanged.emit())

    def on_ratio_changed(self) -> None:
        if self.ratio_combo.currentData() is not None:
            self.apply_ratio_size()

    def apply_ratio_size(self) -> None:
        ratio = self.ratio_combo.currentData()
        if ratio is None or self._syncing_size:
            return
        ratio_w, ratio_h = ratio
        long_edge = self.long_edge_spin.value()
        if ratio_w >= ratio_h:
            width = long_edge
            height = round(long_edge * ratio_h / ratio_w)
        else:
            height = long_edge
            width = round(long_edge * ratio_w / ratio_h)
        self._syncing_size = True
        self.output_width_spin.setValue(width)
        self.output_height_spin.setValue(height)
        self._syncing_size = False

    def on_manual_size_changed(self) -> None:
        if self._syncing_size:
            return
        self._syncing_size = True
        self.set_combo_value(self.ratio_combo, None)
        self.long_edge_spin.setValue(max(self.output_width_spin.value(), self.output_height_spin.value()))
        self._syncing_size = False

    def set_combo_value(self, widget: QComboBox, value) -> None:
        for index in range(widget.count()):
            if widget.itemData(index) == value:
                widget.setCurrentIndex(index)
                return

    def current_layout(self) -> CollageLayout:
        return self.layout_combo.currentData() or COLLAGE_LAYOUTS[0]

    def options(self) -> CollageOptions:
        return CollageOptions(
            gap=int(self.gap_slider.value()),
            corner_radius=int(self.corner_radius_slider.value()),
            background_color=self.background_color_input.text(),
            output_width=self.output_width_spin.value(),
            output_height=self.output_height_spin.value(),
        )

    def settings_values(self) -> dict[str, object]:
        ratio = self.ratio_combo.currentData()
        ratio_value = "custom" if ratio is None else f"{ratio[0]}:{ratio[1]}"
        return {
            "layout": self.current_layout().name,
            "ratio": ratio_value,
            "long_edge": self.long_edge_spin.value(),
            "output_width": self.output_width_spin.value(),
            "output_height": self.output_height_spin.value(),
            "gap": int(self.gap_slider.value()),
            "corner_radius": int(self.corner_radius_slider.value()),
            "background_color": self.background_color_input.text(),
            "jpg_quality": self.quality_spin.value(),
        }

    def restore_settings_values(self, values: dict[str, object]) -> None:
        self.set_combo_text(self.layout_combo, str(values.get("layout", "")))
        self.set_ratio_value(str(values.get("ratio", "1:1")))
        self.set_spin_value(self.long_edge_spin, values.get("long_edge"))
        self.set_spin_value(self.output_width_spin, values.get("output_width"))
        self.set_spin_value(self.output_height_spin, values.get("output_height"))
        self.set_numeric_value(self.gap_slider, values.get("gap"))
        self.set_numeric_value(self.corner_radius_slider, values.get("corner_radius"))
        if "background_color" in values:
            self.background_color_input.setText(str(values["background_color"]))
        self.set_spin_value(self.quality_spin, values.get("jpg_quality"))

    def apply_group_values(self, layout_name: str, options: CollageOptions) -> None:
        values = options_to_dict(options)
        values["layout"] = layout_name
        values["ratio"] = "custom"
        values["long_edge"] = max(options.output_width, options.output_height)
        self.restore_settings_values(values)

    def set_quality(self, quality: int) -> None:
        self.quality_spin.setValue(max(self.quality_spin.minimum(), min(self.quality_spin.maximum(), int(quality))))

    def set_ratio_value(self, value: str) -> None:
        if value == "custom":
            self.set_combo_value(self.ratio_combo, None)
            return
        for index in range(self.ratio_combo.count()):
            ratio = self.ratio_combo.itemData(index)
            if ratio is not None and f"{ratio[0]}:{ratio[1]}" == value:
                self.ratio_combo.setCurrentIndex(index)
                return

    def set_combo_text(self, widget: QComboBox, text: str) -> None:
        if not text:
            return
        for index in range(widget.count()):
            if widget.itemText(index) == text:
                widget.setCurrentIndex(index)
                return

    def set_spin_value(self, widget: QSpinBox, value) -> None:
        if value is None:
            return
        try:
            widget.setValue(int(float(value)))
        except (TypeError, ValueError):
            return

    def set_numeric_value(self, widget: NumericSlider, value) -> None:
        if value is None:
            return
        try:
            widget.setValue(float(value))
        except (TypeError, ValueError):
            return
