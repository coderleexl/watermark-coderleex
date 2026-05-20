from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from watermark_app.core.batch_rename import build_rename_plan, safe_stem, unique_filename
from watermark_app.core.contact_sheet import ContactSheetOptions, create_contact_sheet
from watermark_app.core.social_export import SOCIAL_PRESETS, SocialExportOptions, export_social_image, fit_image


class PhotoToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.first = self.base / "a.jpg"
        self.second = self.base / "b.jpg"
        Image.new("RGB", (600, 400), "red").save(self.first)
        Image.new("RGB", (400, 600), "blue").save(self.second)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_contact_sheet_size(self) -> None:
        image = create_contact_sheet(
            [self.first, self.second],
            ContactSheetOptions(columns=2, thumb_width=200, thumb_height=120, gap=10, margin=20),
        )
        self.assertEqual(image.size, (450, 192))

    def test_social_export_contain_and_cover(self) -> None:
        source = Image.new("RGB", (600, 400), "red").convert("RGBA")
        contain = fit_image(source, 300, 300, "contain", "#ffffff")
        cover = fit_image(source, 300, 300, "cover", "#ffffff")
        self.assertEqual(contain.size, (300, 300))
        self.assertEqual(cover.size, (300, 300))
        out = self.base / "social.jpg"
        rendered = export_social_image(self.first, out, SocialExportOptions(preset=SOCIAL_PRESETS[2]))
        self.assertEqual(rendered.size, (1080, 1080))
        self.assertTrue(out.exists())

    def test_batch_rename_plan(self) -> None:
        plan = build_rename_plan([self.first, self.second], "project_{index}_{stem}", 7)
        self.assertEqual(plan[0].target.name, "project_007_a.jpg")
        self.assertEqual(plan[1].target.name, "project_008_b.jpg")
        self.assertEqual(safe_stem('a/b c'), "a_b_c")
        used: set[str] = set()
        self.assertEqual(unique_filename("a.jpg", used), "a.jpg")
        self.assertEqual(unique_filename("a.jpg", used), "a_2.jpg")


if __name__ == "__main__":
    unittest.main()
