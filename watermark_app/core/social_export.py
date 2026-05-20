from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from watermark_app.core.contact_sheet import parse_color


@dataclass(frozen=True)
class SocialPreset:
    name: str
    width: int
    height: int


SOCIAL_PRESETS = [
    SocialPreset("小红书 3:4", 1440, 1920),
    SocialPreset("小红书 4:5", 1440, 1800),
    SocialPreset("Instagram 1:1", 1080, 1080),
    SocialPreset("Instagram 4:5", 1080, 1350),
    SocialPreset("Story / Reels 9:16", 1080, 1920),
    SocialPreset("YouTube / B站封面 16:9", 1920, 1080),
]


@dataclass
class SocialExportOptions:
    preset: SocialPreset = SOCIAL_PRESETS[0]
    background_color: str = "#ffffff"
    fit_mode: str = "contain"
    quality: int = 92


def export_social_image(source_path: Path, output_path: Path, options: SocialExportOptions) -> Image.Image:
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    rendered = fit_image(image, options.preset.width, options.preset.height, options.fit_mode, options.background_color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        rendered.convert("RGB").save(output_path, quality=options.quality, optimize=True)
    else:
        rendered.save(output_path)
    return rendered


def fit_image(image: Image.Image, width: int, height: int, fit_mode: str, background_color: str) -> Image.Image:
    if fit_mode == "cover":
        scale = max(width / image.width, height / image.height)
    else:
        scale = min(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    if fit_mode == "cover":
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        return resized.crop((left, top, left + width, top + height))
    canvas = Image.new("RGBA", (width, height), parse_color(background_color))
    canvas.alpha_composite(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def preset_by_name(name: str) -> SocialPreset:
    for preset in SOCIAL_PRESETS:
        if preset.name == name:
            return preset
    return SOCIAL_PRESETS[0]
