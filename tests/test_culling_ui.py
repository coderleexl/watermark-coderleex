from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from watermark_app.ui.culling_page import PhotoCullingPage


class CullingUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.image = self.base / "a.jpg"
        Image.new("RGB", (120, 90), "red").save(self.image)
        self.settings_path = str(self.base / "settings.ini")
        self.settings = QSettings(self.settings_path, QSettings.IniFormat)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_page_restores_and_updates_pick(self) -> None:
        page = PhotoCullingPage(self.settings, {".jpg"})
        page.store.add_paths([str(self.image)], {".jpg"})
        page.save()
        page.refresh_list(select_first=True)
        self.assertEqual(page.photo_list.count(), 1)

        page.rating_spin.setValue(4)
        page.set_combo_value(page.status_combo, "保留")
        pick = page.store.by_path(self.image)
        self.assertIsNotNone(pick)
        self.assertEqual(pick.rating, 4)
        self.assertEqual(pick.status, "保留")

        restored = PhotoCullingPage(self.settings, {".jpg"})
        self.assertEqual(len(restored.store.picks), 1)
        self.assertEqual(restored.store.picks[0].rating, 4)


if __name__ == "__main__":
    unittest.main()
