from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from watermark_app.core.collage import COLLAGE_LAYOUTS, CollageOptions
from watermark_app.ui.collage_panel import CollagePanel
from watermark_app.ui.collage_selector import CollagePhotoSelector


class CollageUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.paths = []
        for index, (size, color) in enumerate([((300, 200), "red"), ((200, 300), "green"), ((300, 300), "blue")]):
            path = self.base / f"{index}.jpg"
            Image.new("RGB", size, color).save(path)
            self.paths.append(path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_selector_sets_selected_photos_in_order(self) -> None:
        selector = CollagePhotoSelector({".jpg"})
        selector.add_files([str(path) for path in self.paths])
        selector.set_selected_photos([self.paths[2], self.paths[0]])
        self.assertEqual(selector.selected_photos(), [self.paths[2], self.paths[0]])
        self.assertEqual(len(selector.available_photo_items()), 3)

    def test_panel_applies_group_values(self) -> None:
        panel = CollagePanel()
        options = CollageOptions(gap=24, corner_radius=12, background_color="#123456", output_width=1400, output_height=900)
        panel.apply_group_values(COLLAGE_LAYOUTS[3].name, options)
        panel.set_quality(87)
        self.assertEqual(panel.current_layout().name, COLLAGE_LAYOUTS[3].name)
        self.assertEqual(panel.options().gap, 24)
        self.assertEqual(panel.options().corner_radius, 12)
        self.assertEqual(panel.options().background_color, "#123456")
        self.assertEqual(panel.options().output_width, 1400)
        self.assertEqual(panel.options().output_height, 900)
        self.assertEqual(panel.quality_spin.value(), 87)


if __name__ == "__main__":
    unittest.main()
