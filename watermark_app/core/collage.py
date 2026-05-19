from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


class CollageFitMode(str, Enum):
    COVER = "cover"


@dataclass(frozen=True)
class CollageLayout:
    name: str
    rows: int
    cols: int

    @property
    def cell_count(self) -> int:
        return self.rows * self.cols


@dataclass
class CollageOptions:
    gap: int = 8
    corner_radius: int = 0
    background_color: str = "#ffffff"
    output_width: int = 2000
    output_height: int = 2000
    fit_mode: CollageFitMode = CollageFitMode.COVER


COLLAGE_LAYOUTS = [
    CollageLayout("2张 横排", rows=1, cols=2),
    CollageLayout("2张 竖排", rows=2, cols=1),
    CollageLayout("3张 横排", rows=1, cols=3),
    CollageLayout("4张 2x2", rows=2, cols=2),
    CollageLayout("6张 2x3", rows=2, cols=3),
    CollageLayout("6张 3x2", rows=3, cols=2),
    CollageLayout("9张 3x3", rows=3, cols=3),
]


class CollageEngine:
    def create_collage(
        self,
        images: list[Image.Image],
        layout: CollageLayout,
        options: CollageOptions,
    ) -> Image.Image:
        width = max(1, int(options.output_width))
        height = max(1, int(options.output_height))
        gap = max(0, int(options.gap))
        background = _parse_color(options.background_color)
        canvas = Image.new("RGBA", (width, height), background)

        for image, box in zip(images[: layout.cell_count], calculate_cells(layout, width, height, gap)):
            x, y, cell_width, cell_height = box
            if cell_width <= 0 or cell_height <= 0:
                continue
            tile = cover_crop(image.convert("RGBA"), cell_width, cell_height)
            if options.corner_radius > 0:
                mask = rounded_mask(tile.size, options.corner_radius)
                canvas.paste(tile, (x, y), mask)
            else:
                canvas.alpha_composite(tile, (x, y))
        return canvas

    def create_collage_from_paths(
        self,
        paths: list[Path],
        layout: CollageLayout,
        options: CollageOptions,
        max_source_edge: int | None = None,
    ) -> Image.Image:
        images: list[Image.Image] = []
        for path in paths[: layout.cell_count]:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGBA")
            if max_source_edge and max(image.size) > max_source_edge:
                image.thumbnail((max_source_edge, max_source_edge), Image.Resampling.LANCZOS)
            images.append(image)
        return self.create_collage(images, layout, options)


def calculate_cells(
    layout: CollageLayout,
    output_width: int,
    output_height: int,
    gap: int,
) -> list[tuple[int, int, int, int]]:
    cols = max(1, layout.cols)
    rows = max(1, layout.rows)
    gap = max(0, gap)
    cell_width = (output_width - gap * (cols + 1)) / cols
    cell_height = (output_height - gap * (rows + 1)) / rows
    cells: list[tuple[int, int, int, int]] = []
    for index in range(rows * cols):
        row = index // cols
        col = index % cols
        x = gap + col * (cell_width + gap)
        y = gap + row * (cell_height + gap)
        cells.append((round(x), round(y), max(1, round(cell_width)), max(1, round(cell_height))))
    return cells


def cover_crop(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    scale = max(target_width / image.width, target_height / image.height)
    resized_width = max(1, round(image.width * scale))
    resized_height = max(1, round(image.height * scale))
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=max(0, radius), fill=255)
    return mask


def _parse_color(value: str) -> tuple[int, int, int, int]:
    text = (value or "#ffffff").strip()
    if text.startswith("#"):
        text = text[1:]
    try:
        if len(text) == 3:
            r, g, b = (int(char * 2, 16) for char in text)
            return r, g, b, 255
        if len(text) == 6:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255
        if len(text) == 8:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16)
    except ValueError:
        pass
    return 255, 255, 255, 255
