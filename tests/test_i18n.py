from __future__ import annotations

import unittest

from watermark_app.core.i18n import LANGUAGE_EN, LANGUAGE_ZH, set_language, tr


class I18nTest(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(LANGUAGE_ZH)

    def test_translates_known_keys(self) -> None:
        set_language(LANGUAGE_ZH)
        self.assertEqual(tr("app.collage"), "拼图")
        set_language(LANGUAGE_EN)
        self.assertEqual(tr("app.collage"), "Collage")

    def test_falls_back_to_chinese_or_key(self) -> None:
        set_language("unknown")
        self.assertEqual(tr("app.watermark"), "水印")
        self.assertEqual(tr("missing.key"), "missing.key")


if __name__ == "__main__":
    unittest.main()
