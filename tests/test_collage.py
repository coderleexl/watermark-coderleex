from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from watermark_app.core.collage import COLLAGE_LAYOUTS, CollageEngine, CollageOptions, calculate_cells, cover_crop
from watermark_app.core.collage_groups import CollageGroup, CollageGroupStore, layout_by_name, safe_filename
from watermark_app.core.renderer import save_rendered


class CollageEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.paths = self.make_images()
        self.engine = CollageEngine()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_images(self) -> list[Path]:
        specs = [
            ((900, 600), (220, 40, 40)),
            ((600, 900), (40, 160, 80)),
            ((800, 800), (50, 90, 220)),
            ((1000, 650), (230, 190, 40)),
            ((650, 1000), (150, 70, 210)),
            ((1100, 700), (40, 180, 190)),
            ((700, 1100), (130, 130, 130)),
            ((850, 620), (220, 120, 40)),
            ((620, 850), (220, 80, 140)),
            ((780, 780), (20, 150, 140)),
        ]
        paths: list[Path] = []
        for index, (size, color) in enumerate(specs):
            path = self.base / f"{index:02d}.jpg"
            Image.new("RGB", size, color).save(path, quality=95)
            paths.append(path)
        return paths

    def test_output_sizes_for_common_layouts(self) -> None:
        cases = [
            (0, self.paths[:2], (1600, 800)),
            (3, self.paths[:4], (1200, 1200)),
            (6, self.paths[:9], (1800, 1800)),
        ]
        for layout_index, paths, size in cases:
            with self.subTest(layout=COLLAGE_LAYOUTS[layout_index].name):
                image = self.engine.create_collage_from_paths(
                    paths,
                    COLLAGE_LAYOUTS[layout_index],
                    CollageOptions(output_width=size[0], output_height=size[1], gap=16, corner_radius=12),
                    max_source_edge=500,
                )
                self.assertEqual(image.size, size)

    def test_sparse_cells_keep_background(self) -> None:
        image = self.engine.create_collage_from_paths(
            self.paths[:2],
            COLLAGE_LAYOUTS[3],
            CollageOptions(output_width=1000, output_height=1000, gap=20, background_color="#123456"),
        )
        self.assertEqual(image.size, (1000, 1000))
        self.assertEqual(image.getpixel((750, 750))[:3], (18, 52, 86))

    def test_extra_images_are_ignored(self) -> None:
        image = self.engine.create_collage_from_paths(
            self.paths[:5],
            COLLAGE_LAYOUTS[3],
            CollageOptions(output_width=1000, output_height=1000, gap=20),
        )
        self.assertEqual(image.size, (1000, 1000))

    def test_cell_calculation(self) -> None:
        self.assertEqual(
            calculate_cells(COLLAGE_LAYOUTS[3], 1000, 1000, 20),
            [(20, 20, 470, 470), (510, 20, 470, 470), (20, 510, 470, 470), (510, 510, 470, 470)],
        )

    def test_cover_crop_fills_target(self) -> None:
        wide = Image.new("RGB", (1200, 600), "red")
        tall = Image.new("RGB", (600, 1200), "blue")
        self.assertEqual(cover_crop(wide, 300, 300).size, (300, 300))
        self.assertEqual(cover_crop(tall, 300, 300).size, (300, 300))

    def test_save_png_and_jpg(self) -> None:
        image = self.engine.create_collage_from_paths(
            self.paths[:4],
            COLLAGE_LAYOUTS[3],
            CollageOptions(output_width=1000, output_height=1000, gap=20),
        )
        png_out = self.base / "collage.png"
        jpg_out = self.base / "collage.jpg"
        save_rendered(image, png_out)
        save_rendered(image, jpg_out, quality=90)
        self.assertGreater(png_out.stat().st_size, 0)
        self.assertGreater(jpg_out.stat().st_size, 0)


class CollageGroupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.existing = self.base / "existing.jpg"
        Image.new("RGB", (400, 300), "red").save(self.existing)
        self.missing = self.base / "missing.jpg"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_group_json_discards_missing_paths_and_empty_groups(self) -> None:
        valid_group = CollageGroup.create(
            "有效组",
            [self.existing, self.missing],
            COLLAGE_LAYOUTS[3],
            CollageOptions(output_width=1200, output_height=900),
            jpg_quality=88,
        )
        invalid_group = CollageGroup.create(
            "失效组",
            [self.missing],
            COLLAGE_LAYOUTS[0],
            CollageOptions(),
        )
        text = CollageGroupStore([valid_group, invalid_group]).to_json()
        restored = CollageGroupStore.from_json(text, {".jpg"})
        self.assertEqual(len(restored.groups), 1)
        self.assertEqual(restored.groups[0].name, "有效组")
        self.assertEqual(restored.groups[0].photo_paths, [str(self.existing)])
        self.assertEqual(restored.groups[0].jpg_quality, 88)
        self.assertEqual(restored.groups[0].options.output_width, 1200)

    def test_safe_filename_cleans_illegal_chars_and_deduplicates(self) -> None:
        used: set[str] = set()
        first = safe_filename('a/b:c*?"<>|', used)
        second = safe_filename('a/b:c*?"<>|', used)
        self.assertEqual(first, "a_b_c_.jpg")
        self.assertEqual(second, "a_b_c__2.jpg")

    def test_layout_by_name_falls_back(self) -> None:
        self.assertEqual(layout_by_name("4张 2x2").cell_count, 4)
        self.assertEqual(layout_by_name("不存在").name, COLLAGE_LAYOUTS[0].name)

    def test_copy_duplicate_name_and_reorder(self) -> None:
        first = CollageGroup.create("拼图组", [self.existing], COLLAGE_LAYOUTS[0], CollageOptions(gap=20))
        store = CollageGroupStore([first])
        copied = first.copy(store.duplicate_name(first.name))
        store.groups.append(copied)
        self.assertNotEqual(first.id, copied.id)
        self.assertEqual(copied.name, "拼图组 副本")
        self.assertEqual(copied.options.gap, 20)
        store.reorder([copied.id, first.id])
        self.assertEqual([group.id for group in store.groups], [copied.id, first.id])

    def test_safe_filename_supports_png_suffix(self) -> None:
        used: set[str] = set()
        self.assertEqual(safe_filename("导出/组", used, ".png"), "导出_组.png")


if __name__ == "__main__":
    unittest.main()
