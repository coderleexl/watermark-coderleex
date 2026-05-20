from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass
class ContactSheetOptions:
    columns: int = 4
    thumb_width: int = 360
    thumb_height: int = 240
    gap: int = 24
    margin: int = 36
    background_color: str = "#ffffff"
    text_color: str = "#222222"
    show_filename: bool = True


def create_contact_sheet(paths: list[Path], options: ContactSheetOptions) -> Image.Image:
    columns = max(1, int(options.columns))
    count = len(paths)
    rows = max(1, (count + columns - 1) // columns)
    label_height = 32 if options.show_filename else 0
    cell_width = max(1, options.thumb_width)
    cell_height = max(1, options.thumb_height) + label_height
    width = options.margin * 2 + columns * cell_width + (columns - 1) * options.gap
    height = options.margin * 2 + rows * cell_height + (rows - 1) * options.gap
    canvas = Image.new("RGBA", (width, height), parse_color(options.background_color))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    text_color = parse_color(options.text_color)

    for index, path in enumerate(paths):
        row = index // columns
        col = index % columns
        x = options.margin + col * (cell_width + options.gap)
        y = options.margin + row * (cell_height + options.gap)
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((options.thumb_width, options.thumb_height), Image.Resampling.LANCZOS)
        image_x = x + (options.thumb_width - image.width) // 2
        image_y = y + (options.thumb_height - image.height) // 2
        canvas.alpha_composite(image, (image_x, image_y))
        if options.show_filename:
            label = path.name
            draw.text((x, y + options.thumb_height + 8), label[:48], fill=text_color, font=font)
    return canvas


def parse_color(value: str) -> tuple[int, int, int, int]:
    text = (value or "#ffffff").strip()
    if text.startswith("#"):
        text = text[1:]
    try:
        if len(text) == 6:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255
        if len(text) == 3:
            r, g, b = (int(char * 2, 16) for char in text)
            return r, g, b, 255
    except ValueError:
        pass
    return 255, 255, 255, 255
