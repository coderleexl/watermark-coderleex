from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from watermark_app.core.collage import COLLAGE_LAYOUTS, CollageEngine, CollageOptions, calculate_cells
from watermark_app.core.renderer import save_rendered


def make_sample_images(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    specs = [
        ("red", (900, 600), (220, 40, 40)),
        ("green", (600, 900), (40, 160, 80)),
        ("blue", (800, 800), (50, 90, 220)),
        ("yellow", (1000, 650), (230, 190, 40)),
        ("purple", (650, 1000), (150, 70, 210)),
        ("cyan", (1100, 700), (40, 180, 190)),
        ("gray", (700, 1100), (130, 130, 130)),
        ("orange", (850, 620), (220, 120, 40)),
        ("pink", (620, 850), (220, 80, 140)),
        ("teal", (780, 780), (20, 150, 140)),
    ]
    paths: list[Path] = []
    for index, (name, size, color) in enumerate(specs):
        path = directory / f"{index:02d}_{name}.jpg"
        Image.new("RGB", size, color).save(path, quality=95)
        paths.append(path)
    return paths


def assert_size(engine: CollageEngine, paths: list[Path], layout_index: int, size: tuple[int, int]) -> None:
    image = engine.create_collage_from_paths(
        paths,
        COLLAGE_LAYOUTS[layout_index],
        CollageOptions(output_width=size[0], output_height=size[1], gap=16, corner_radius=12),
        max_source_edge=500,
    )
    assert image.size == size, f"expected {size}, got {image.size}"


def main() -> None:
    base = Path("/private/tmp/watermark_collage_smoke")
    paths = make_sample_images(base)
    engine = CollageEngine()

    assert_size(engine, paths[:2], 0, (1600, 800))
    assert_size(engine, paths[:4], 3, (1200, 1200))
    assert_size(engine, paths[:9], 6, (1800, 1800))

    # Fewer images than cells should leave background cells without failing.
    sparse = engine.create_collage_from_paths(
        paths[:2],
        COLLAGE_LAYOUTS[3],
        CollageOptions(output_width=1000, output_height=1000, gap=20, background_color="#123456"),
    )
    assert sparse.size == (1000, 1000)
    assert sparse.getpixel((750, 750))[:3] == (18, 52, 86)

    # More images than cells should ignore extras.
    extra = engine.create_collage_from_paths(
        paths[:5],
        COLLAGE_LAYOUTS[3],
        CollageOptions(output_width=1000, output_height=1000, gap=20),
    )
    assert extra.size == (1000, 1000)

    cells = calculate_cells(COLLAGE_LAYOUTS[3], 1000, 1000, 20)
    assert cells == [(20, 20, 470, 470), (510, 20, 470, 470), (20, 510, 470, 470), (510, 510, 470, 470)]

    png_out = base / "collage.png"
    jpg_out = base / "collage.jpg"
    save_rendered(extra, png_out)
    save_rendered(extra, jpg_out, quality=90)
    assert png_out.exists() and png_out.stat().st_size > 0
    assert jpg_out.exists() and jpg_out.stat().st_size > 0

    print(f"collage smoke ok: {png_out} {jpg_out}")


if __name__ == "__main__":
    main()
