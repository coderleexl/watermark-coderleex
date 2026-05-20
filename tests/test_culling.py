from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from watermark_app.core.culling import CullingStore, PhotoPick, copy_picks_to_directory, unique_name


class CullingStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.first = self.base / "a.jpg"
        self.second = self.base / "b.png"
        Image.new("RGB", (100, 80), "red").save(self.first)
        Image.new("RGB", (80, 100), "blue").save(self.second)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_round_trip_discards_missing_files(self) -> None:
        store = CullingStore([
            PhotoPick(str(self.first), rating=3, color_label="红", status="保留"),
            PhotoPick(str(self.base / "missing.jpg"), rating=5, status="保留"),
        ])
        restored = CullingStore.from_json(store.to_json(), {".jpg", ".png"})
        self.assertEqual(len(restored.picks), 1)
        self.assertEqual(restored.picks[0].rating, 3)
        self.assertEqual(restored.picks[0].color_label, "红")
        self.assertEqual(restored.picks[0].status, "保留")

    def test_add_paths_deduplicates_and_filters_extensions(self) -> None:
        other = self.base / "note.txt"
        other.write_text("x")
        store = CullingStore()
        self.assertTrue(store.add_paths([str(self.first), str(self.first), str(other)], {".jpg", ".png"}))
        self.assertEqual(len(store.picks), 1)
        self.assertFalse(store.add_paths([str(other)], {".jpg", ".png"}))

    def test_filter_and_delivery_selection(self) -> None:
        store = CullingStore([
            PhotoPick(str(self.first), rating=0, status="保留"),
            PhotoPick(str(self.second), rating=4, status="未定"),
            PhotoPick(str(self.base / "c.jpg"), rating=1, status="淘汰"),
        ])
        self.assertEqual([pick.path for pick in store.filtered(minimum_rating=3)], [str(self.second)])
        self.assertEqual(len(store.filtered(status="保留")), 1)
        self.assertEqual(len(store.selected_for_delivery()), 3)

    def test_copy_picks_to_directory_uses_unique_names(self) -> None:
        duplicate = self.base / "nested"
        duplicate.mkdir()
        same_name = duplicate / self.first.name
        Image.new("RGB", (100, 80), "green").save(same_name)
        output = self.base / "out"
        copied = copy_picks_to_directory(
            [PhotoPick(str(self.first)), PhotoPick(str(same_name))],
            output,
        )
        self.assertEqual([path.name for path in copied], ["a.jpg", "a_2.jpg"])
        self.assertTrue(all(path.exists() for path in copied))

    def test_unique_name(self) -> None:
        used: set[str] = set()
        self.assertEqual(unique_name("a.jpg", used), "a.jpg")
        self.assertEqual(unique_name("a.jpg", used), "a_2.jpg")


if __name__ == "__main__":
    unittest.main()
