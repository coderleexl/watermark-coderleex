from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image
from PIL.ImageQt import fromqimage
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


LOGO_DIR = Path(__file__).resolve().parents[2] / "assets" / "logos"


def load_brand_logo(brand: str, variant: str, width: int, height: int) -> Image.Image | None:
    slug = _brand_slug(brand)
    if not slug:
        return None
    path = LOGO_DIR / f"{slug}-{'w' if variant == 'white' else 'b'}.svg"
    if not path.exists():
        return None
    return _render_svg(path, max(1, width), max(1, height))


def _brand_slug(brand: str) -> str:
    text = (brand or "").strip().lower()
    mapping = {
        "sony": "sony",
        "nikon": "nikon",
        "canon": "canon",
        "leica": "leica",
        "hasselblad": "hasselblad",
        "fujifilm": "fujifilm",
        "fuji": "fujifilm",
        "ricoh": "ricoh",
        "pentax": "pentax",
        "panasonic": "panasonic",
        "olympus": "olympus",
        "dji": "dji",
        "sigma": "sigma",
    }
    return mapping.get(text, "")


@lru_cache(maxsize=128)
def _render_svg(path: Path, width: int, height: int) -> Image.Image | None:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None
    default_size = renderer.defaultSize()
    if default_size.width() > 0 and default_size.height() > 0:
        ratio = default_size.width() / default_size.height()
        width = min(width, max(1, int(height * ratio)))
        height = min(height, max(1, int(width / ratio)))
    qimage = QImage(width, height, QImage.Format_ARGB32)
    qimage.fill(0)
    painter = QPainter(qimage)
    renderer.render(painter)
    painter.end()
    return fromqimage(qimage).convert("RGBA")
