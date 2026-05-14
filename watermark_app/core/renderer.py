from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from watermark_app.core.exif import PhotoMetadata
from watermark_app.core.formatter import format_metadata_template
from watermark_app.core.logos import load_brand_logo
from watermark_app.core.templates import RenderOptions, TemplateKind, WatermarkPosition


FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]

ITALIC_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
]

TITLE_FONTS = [
    ("默认", []),
    ("Baskerville 古典衬线", ["/System/Library/Fonts/Supplemental/Baskerville.ttc"]),
    ("Didot 时尚衬线", ["/System/Library/Fonts/Supplemental/Didot.ttc"]),
    ("Palatino 帕拉提诺", ["/System/Library/Fonts/Supplemental/Palatino.ttc"]),
    ("Times New Roman 衬线", ["/System/Library/Fonts/Supplemental/Times New Roman.ttf"]),
    ("Georgia 乔治亚", ["/System/Library/Fonts/Supplemental/Georgia.ttf"]),
    ("Futura 未来", ["/System/Library/Fonts/Supplemental/Futura.ttc"]),
    ("Avenir 阿文尼", ["/System/Library/Fonts/Avenir.ttc", "/System/Library/Fonts/Supplemental/Avenir.ttc"]),
    ("Helvetica Neue 海维提卡", ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Supplemental/HelveticaNeue.ttc"]),
    ("Impact 粗体", ["/System/Library/Fonts/Supplemental/Impact.ttf"]),
    ("Copperplate 铜板雕刻", ["/System/Library/Fonts/Supplemental/Copperplate.ttc"]),
    ("Zapfino 花体", ["/System/Library/Fonts/Zapfino.ttf", "/System/Library/Fonts/Supplemental/Zapfino.ttf"]),
    ("Snell Roundhand 花体", ["/System/Library/Fonts/Supplemental/Snell Roundhand.ttc"]),
    ("Apple Chancery 草书", ["/System/Library/Fonts/Supplemental/Apple Chancery.ttf"]),
    ("Brush Script 手写", ["/System/Library/Fonts/Supplemental/Brush Script.ttf"]),
    ("Noteworthy 随手写", ["/System/Library/Fonts/Noteworthy.ttc", "/System/Library/Fonts/Supplemental/Noteworthy.ttc"]),
    ("Marker Felt 马克笔", ["/System/Library/Fonts/MarkerFelt.ttc", "/System/Library/Fonts/Supplemental/MarkerFelt.ttc"]),
    ("Papyrus 羊皮纸", ["/System/Library/Fonts/Supplemental/Papyrus.ttc"]),
    ("Chalkduster 粉笔", ["/System/Library/Fonts/Supplemental/Chalkduster.ttf"]),
    ("Courier New 等宽", ["/System/Library/Fonts/Supplemental/Courier New.ttf"]),
]


def render_image(
    source_path: str | Path,
    options: RenderOptions,
    metadata: PhotoMetadata,
    max_source_edge: int | None = None,
) -> Image.Image:
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    if max_source_edge and max(image.size) > max_source_edge:
        image.thumbnail((max_source_edge, max_source_edge), resample=Image.Resampling.LANCZOS)

    return render_image_bitmap(image, options, metadata)


def render_image_bitmap(image: Image.Image, options: RenderOptions, metadata: PhotoMetadata) -> Image.Image:
    canvas = image
    if options.enable_camera_info and options.template != TemplateKind.NONE:
        if options.template == TemplateKind.LEICA_FRAME:
            canvas = _render_frame(image, options, metadata, background=_parse_color(options.background_color, (248, 247, 244, 255)), foreground=(20, 20, 20, 255), accent=(166, 121, 44, 255))
        elif options.template == TemplateKind.HASSELBLAD_FRAME:
            canvas = _render_hasselblad_caption(image, options, metadata)
        elif options.template == TemplateKind.BLUR_FRAME:
            canvas = _render_blur_frame(image, options, metadata)

    if options.enable_signature:
        canvas = _render_signature_watermark(canvas, options, metadata)
    return canvas


def save_rendered(image: Image.Image, output_path: str | Path, quality: int = 95) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        image.convert("RGB").save(output, quality=quality, optimize=True)
    else:
        image.save(output)


def _render_frame(
    image: Image.Image,
    options: RenderOptions,
    metadata: PhotoMetadata,
    background: tuple[int, int, int, int],
    foreground: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> Image.Image:
    main = _prepare_main_image(image, options)
    width, height = main.size
    side = max(24, int(width * options.border_percent))
    top = max(24, int(height * options.border_percent))
    bottom = max(96, int(height * options.bottom_percent))
    shadow = _shadow_layer(main.size, options)
    shadow_pad = max(0, int(height * options.shadow_percent)) if shadow else 0
    canvas = Image.new("RGBA", (width + side * 2 + shadow_pad * 2, height + top + bottom + shadow_pad * 2), background)
    image_x = side + shadow_pad
    image_y = top + shadow_pad
    if shadow:
        canvas.alpha_composite(shadow, (image_x - shadow_pad, image_y - shadow_pad))
    canvas.alpha_composite(main, (image_x, image_y))

    draw = ImageDraw.Draw(canvas)
    title_size = max(28, int(canvas.width * 0.032 * options.text_scale))
    detail_size = max(13, int(canvas.width * 0.012 * options.text_scale))
    small_size = max(11, int(canvas.width * 0.010 * options.text_scale))
    title_font = _load_title_font(title_size, options.title_font_name)
    detail_font = _load_font(detail_size)
    small_font = _load_font(small_size)
    foreground = _with_opacity(foreground, options.opacity)
    title_fill = _with_opacity(foreground, options.title_opacity)
    accent = _with_opacity(accent, options.opacity)

    title = (options.title_text or "CODERLEEX").upper()
    camera_text, lens_text, exposure_text = _frame_metadata_text(options, metadata)
    title_y = image_y + height + max(18, bottom // 5)

    if options.show_title:
        title_width, title_height = _tracking_text_size(draw, title, title_font, tracking=max(5, title_size // 5))
        title_anchor = (canvas.width // 2 - title_width // 2, title_y)
        if options.title_position != WatermarkPosition.BOTTOM_CENTER:
            title_anchor = _position_for(canvas.size, (title_width, title_height), options.title_position, margin=max(20, canvas.width // 36))
        title_anchor = _layer_offset_position(title_anchor, canvas.size, (title_width, title_height), options.title_offset_x_percent, options.title_offset_y_percent)
        _draw_tracking(draw, title, title_anchor, title_font, title_fill, tracking=max(5, title_size // 5))

    line_y = title_y + title_size + max(14, bottom // 8)
    line_width = min(canvas.width // 4, 260)
    if options.show_title:
        draw.line((canvas.width // 2 - line_width // 2, line_y, canvas.width // 2 + line_width // 2, line_y), fill=accent, width=max(1, canvas.width // 900))

    side_y = min(canvas.height - small_size * 2 - max(18, bottom // 8), line_y)
    side_margin = side + shadow_pad
    logo_variant = "white" if sum(foreground[:3]) > 384 else "black"
    logo = _brand_logo_for_canvas(metadata, logo_variant, canvas.size, options)
    make_model_text = " · ".join(part for part in [camera_text, lens_text] if part)
    params_text = exposure_text
    if logo and options.show_brand_logo and options.logo_position != WatermarkPosition.BOTTOM_LEFT:
        anchor = _position_for(canvas.size, logo.size, options.logo_position, margin=max(20, canvas.width // 36))
    else:
        anchor = (side_margin, max(image_y + height + 10, side_y - int(small_size * 1.7)))
    _draw_brand_info_block(canvas, draw, anchor, metadata, options, logo_variant, make_model_text, params_text, small_font, foreground)
    return canvas


def _render_blur_frame(image: Image.Image, options: RenderOptions, metadata: PhotoMetadata) -> Image.Image:
    width, height = image.size
    target_ratio = width / height
    canvas_width = max(width, int(width / max(0.45, min(0.96, options.main_image_percent))))
    canvas_height = int(canvas_width / target_ratio)
    extra_bottom = int(height * options.bottom_percent)
    canvas_height = max(canvas_height + extra_bottom, height + extra_bottom + 80)

    background = image.copy()
    background = ImageOps.fit(background, (canvas_width, canvas_height), method=Image.Resampling.LANCZOS)
    blur_radius = max(8, int(min(canvas_width, canvas_height) * max(0.05, min(1.0, options.blur_percent)) * 0.08))
    background = background.filter(ImageFilter.GaussianBlur(blur_radius))
    overlay = Image.new("RGBA", background.size, (0, 0, 0, 68))
    canvas = Image.alpha_composite(background, overlay)

    main = _prepare_main_image(image, options)
    main_target_width = int(canvas_width * max(0.45, min(0.96, options.main_image_percent)))
    if main.width != main_target_width:
        ratio = main_target_width / main.width
        main = main.resize((main_target_width, max(1, int(main.height * ratio))), Image.Resampling.LANCZOS)
    shadow = _shadow_layer(main.size, options)
    shadow_pad = max(0, int(main.height * options.shadow_percent)) if shadow else 0
    x = (canvas_width - main.width) // 2
    y = max(24, int(canvas_height * options.border_percent))
    if shadow:
        canvas.alpha_composite(shadow, (x - shadow_pad, y - shadow_pad))
    canvas.alpha_composite(main, (x, y))

    draw = ImageDraw.Draw(canvas)
    title_font = _load_title_font(max(20, int(canvas_width * 0.026 * options.text_scale)), options.title_font_name)
    detail_font = _load_font(max(11, int(canvas_width * 0.010 * options.text_scale)))
    fill = _with_opacity((255, 255, 255, 255), options.opacity)
    title_fill = _with_opacity(fill, options.title_opacity)
    title = options.title_text.strip() or metadata.brand_label or "CODERLEEX"
    text_y = y + main.height + max(18, int(canvas_height * 0.024))
    if options.show_title:
        title_text = title.upper()
        title_w, title_h = _text_size(draw, title_text, title_font)
        title_anchor = ((canvas_width - title_w) // 2, text_y)
        title_anchor = _layer_offset_position(title_anchor, canvas.size, (title_w, title_h), options.title_offset_x_percent, options.title_offset_y_percent)
        draw.text(title_anchor, title_text, font=title_font, fill=title_fill)
    camera_text, lens_text, exposure_text = _frame_metadata_text(options, metadata)
    block_anchor = ((canvas_width - int(canvas_width * options.logo_scale)) // 2, text_y + int(canvas_width * 0.04))
    _draw_brand_info_block(canvas, draw, block_anchor, metadata, options, "white", " · ".join(part for part in [camera_text, lens_text] if part), exposure_text, detail_font, fill)
    return canvas


def _render_signature_watermark(image: Image.Image, options: RenderOptions, metadata: PhotoMetadata) -> Image.Image:
    if options.png_watermark_path:
        return _render_png_watermark(image, options)
    return _render_text_watermark(image, options, metadata)


def _render_text_watermark(image: Image.Image, options: RenderOptions, metadata: PhotoMetadata) -> Image.Image:
    canvas = image.copy()
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    title_size = max(16, int(canvas.width * 0.026 * options.signature_scale))
    detail_size = max(10, int(canvas.width * 0.010 * options.signature_scale))
    title_font = _load_font(title_size)
    detail_font = _load_font(detail_size)
    alpha = int(255 * max(0.05, min(1.0, options.signature_opacity)))
    fill = (235, 235, 235, alpha)
    shadow = (0, 0, 0, int(alpha * 0.38))

    title = options.signature_text.strip() or "CODERLEEX PHOTOGRAPHY"
    detail = ""
    block_w = max(_text_size(draw, title, title_font)[0], _text_size(draw, detail, detail_font)[0] if detail else 0)
    block_h = title_size + (detail_size + 8 if detail else 0)
    x, y = _position_for(canvas.size, (block_w, block_h), options.signature_position, margin=max(20, canvas.width // 36))
    x, y = _layer_offset_position((x, y), canvas.size, (block_w, block_h), options.signature_offset_x_percent, options.signature_offset_y_percent)

    _draw_text_with_shadow(draw, (x, y), title, title_font, fill, shadow)
    if detail:
        _draw_text_with_shadow(draw, (x, y + title_size + 8), detail, detail_font, fill, shadow)
    return Image.alpha_composite(canvas, overlay)


def _render_hasselblad_caption(image: Image.Image, options: RenderOptions, metadata: PhotoMetadata) -> Image.Image:
    canvas = image.copy()
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    title_size = max(22, int(canvas.width * 0.036 * options.text_scale))
    detail_size = max(10, int(canvas.width * 0.011 * options.text_scale))
    if options.title_font_name:
        title_font = _load_title_font(title_size, options.title_font_name)
    else:
        title_font = _load_font(title_size, italic=True)
    detail_font = _load_font(detail_size)
    alpha = int(255 * max(0.05, min(1.0, options.opacity)))
    fill = (255, 255, 255, alpha)
    shadow = (0, 0, 0, int(alpha * 0.45))

    title = options.title_text.strip() or "Hasselblad"
    title_w, title_h = _text_size(draw, title, title_font)
    gap = max(6, int(canvas.height * 0.008))
    block_h = title_h + gap + detail_size * 3
    base_margin = max(24, int(canvas.height * 0.045))
    y = canvas.height - block_h - base_margin
    title_x = (canvas.width - title_w) // 2

    if options.show_title:
        title_fill = _with_opacity(fill, options.title_opacity)
        title_shadow_alpha = int(shadow[3] * max(0.05, min(1.0, options.title_opacity)))
        title_shadow = (shadow[0], shadow[1], shadow[2], title_shadow_alpha)
        title_anchor = _layer_offset_position((title_x, y), canvas.size, (title_w, title_h), options.title_offset_x_percent, options.title_offset_y_percent)
        _draw_text_with_shadow(draw, title_anchor, title, title_font, title_fill, title_shadow)
    camera_text, lens_text, exposure_text = _frame_metadata_text(options, metadata)
    block_anchor = ((canvas.width - int(canvas.width * options.logo_scale)) // 2, y + title_h + gap)
    composed = Image.alpha_composite(canvas, overlay)
    composed_draw = ImageDraw.Draw(composed)
    _draw_brand_info_block(composed, composed_draw, block_anchor, metadata, options, "white", " · ".join(part for part in [camera_text, lens_text] if part), exposure_text, detail_font, fill)
    return composed


def _with_opacity(color: tuple[int, int, int, int], opacity: float) -> tuple[int, int, int, int]:
    alpha = int(color[3] * max(0.05, min(1.0, opacity)))
    return color[0], color[1], color[2], alpha


def _frame_metadata_text(options: RenderOptions, metadata: PhotoMetadata) -> tuple[str, str, str]:
    manual_subtitle = options.subtitle_text.strip()
    if not options.use_exif:
        return "", manual_subtitle or options.detail_template or "PHOTOGRAPHY", ""
    camera_text = " · ".join(part for part in [metadata.camera_label, metadata.date_taken] if part)
    lens_text = manual_subtitle or metadata.lens_model or "PHOTOGRAPHY"
    exposure_text = metadata.exposure_label
    if not any([camera_text, metadata.lens_model, exposure_text]) and not manual_subtitle:
        lens_text = "PHOTOGRAPHY"
    return camera_text, lens_text, exposure_text


def _draw_camera_param_block(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    line1: str,
    line2: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    max_width: int,
) -> None:
    x, y = xy
    if line1:
        line1_font = _fit_font(draw, line1, font, max_width)
        draw.text((x, y), line1, font=line1_font, fill=fill)
        y += max(_text_size(draw, line1, line1_font)[1], getattr(line1_font, "size", 12)) + 4
    if line2:
        line2_font = _fit_font(draw, line2, font, max_width)
        draw.text((x, y), line2, font=line2_font, fill=fill)


def _draw_brand_info_block(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    anchor_xy: tuple[int, int],
    metadata: PhotoMetadata,
    options: RenderOptions,
    logo_variant: str,
    line1: str,
    line2: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
) -> None:
    if not options.show_brand_logo and not options.show_exif:
        return
    max_width = max(120, canvas.width // 2)
    logo = _brand_logo_for_canvas(metadata, logo_variant, canvas.size, options)
    x, y = anchor_xy
    if logo and options.show_brand_logo:
        logo_xy = _offset_position((x, y), canvas.size, logo.size, options)
        canvas.alpha_composite(_apply_image_opacity(logo, options.opacity), logo_xy)
        text_xy = (logo_xy[0], min(canvas.height - 2 * getattr(font, "size", 12), logo_xy[1] + logo.height + 4))
    else:
        text_xy = _offset_position((x, y), canvas.size, (max_width, getattr(font, "size", 12) * 2), options)
    if options.show_exif:
        text_xy = _position_for(canvas.size, (max_width, getattr(font, "size", 12) * 3), options.exif_position, margin=max(20, canvas.width // 36)) if options.exif_position != options.logo_position else text_xy
        text_xy = _layer_offset_position(text_xy, canvas.size, (max_width, getattr(font, "size", 12) * 3), options.exif_offset_x_percent, options.exif_offset_y_percent)
        exif_font = _font_with_scaled_size(font, options.exif_scale)
        exif_fill = _with_opacity(fill, options.exif_opacity)
        _draw_camera_param_block(draw, text_xy, line1, line2, exif_font, exif_fill, max_width=max_width)


def _inline_metadata_text(options: RenderOptions, metadata: PhotoMetadata) -> str:
    manual_subtitle = options.subtitle_text.strip()
    if manual_subtitle:
        return manual_subtitle
    if not options.use_exif:
        return ""
    return format_metadata_template(options.detail_template, metadata) or metadata.detail_label


def _render_png_watermark(image: Image.Image, options: RenderOptions) -> Image.Image:
    canvas = image.copy()
    if not options.png_watermark_path:
        return canvas
    try:
        watermark = Image.open(options.png_watermark_path).convert("RGBA")
    except Exception:
        return canvas

    target_width = max(24, int(canvas.width * options.signature_scale))
    ratio = target_width / watermark.width
    watermark = watermark.resize((target_width, max(1, int(watermark.height * ratio))), Image.Resampling.LANCZOS)
    if options.signature_opacity < 0.99:
        alpha = watermark.getchannel("A")
        alpha = ImageEnhance.Brightness(alpha).enhance(max(0.05, min(1.0, options.signature_opacity)))
        watermark.putalpha(alpha)

    x, y = _position_for(canvas.size, watermark.size, options.signature_position, margin=max(20, canvas.width // 38))
    x, y = _layer_offset_position((x, y), canvas.size, watermark.size, options.signature_offset_x_percent, options.signature_offset_y_percent)
    canvas.alpha_composite(watermark, (x, y))
    return canvas


def _brand_logo_for_canvas(metadata: PhotoMetadata, variant: str, canvas_size: tuple[int, int], options: RenderOptions) -> Image.Image | None:
    width, height = canvas_size
    logo_width = int(width * max(0.04, min(0.4, options.logo_scale)))
    logo_height = int(height * max(0.018, min(0.16, options.logo_scale * 0.35)))
    return load_brand_logo(metadata.brand_label, variant, logo_width, logo_height)


def _offset_position(
    xy: tuple[int, int],
    canvas_size: tuple[int, int],
    item_size: tuple[int, int],
    options: RenderOptions,
) -> tuple[int, int]:
    x = xy[0] + int(canvas_size[0] * options.logo_offset_x_percent)
    y = xy[1] + int(canvas_size[1] * options.logo_offset_y_percent)
    return (
        max(0, min(canvas_size[0] - item_size[0], x)),
        max(0, min(canvas_size[1] - item_size[1], y)),
    )


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> ImageFont.ImageFont:
    width, _ = _text_size(draw, text, font)
    if width <= max_width or not hasattr(font, "path") or not hasattr(font, "size"):
        return font
    size = int(font.size)
    while size > 8:
        size -= 1
        try:
            candidate = ImageFont.truetype(font.path, size=size)
        except Exception:
            break
        width, _ = _text_size(draw, text, candidate)
        if width <= max_width:
            return candidate
    return font


def _apply_image_opacity(image: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.99:
        return image
    result = image.copy()
    alpha = result.getchannel("A")
    alpha = ImageEnhance.Brightness(alpha).enhance(max(0.05, min(1.0, opacity)))
    result.putalpha(alpha)
    return result


def _layer_offset_position(
    xy: tuple[int, int],
    canvas_size: tuple[int, int],
    item_size: tuple[int, int],
    offset_x_percent: float,
    offset_y_percent: float,
) -> tuple[int, int]:
    x = xy[0] + int(canvas_size[0] * offset_x_percent)
    y = xy[1] + int(canvas_size[1] * offset_y_percent)
    return (
        max(0, min(canvas_size[0] - item_size[0], x)),
        max(0, min(canvas_size[1] - item_size[1], y)),
    )


def _font_with_scaled_size(font: ImageFont.ImageFont, scale: float) -> ImageFont.ImageFont:
    if not hasattr(font, "path") or not hasattr(font, "size"):
        return font
    size = max(8, int(font.size * max(0.35, min(2.5, scale))))
    try:
        return ImageFont.truetype(font.path, size=size)
    except Exception:
        return font


def _prepare_main_image(image: Image.Image, options: RenderOptions) -> Image.Image:
    main = image.copy()
    scale = max(0.2, min(1.0, options.main_image_percent))
    if scale < 0.995:
        main = main.resize((max(1, int(main.width * scale)), max(1, int(main.height * scale))), Image.Resampling.LANCZOS)
    radius = int(min(main.size) * max(0.0, min(0.18, options.corner_radius_percent)))
    if radius <= 0:
        return main
    mask = Image.new("L", main.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, main.width, main.height), radius=radius, fill=255)
    rounded = Image.new("RGBA", main.size, (0, 0, 0, 0))
    rounded.alpha_composite(main)
    rounded.putalpha(mask)
    return rounded


def _shadow_layer(size: tuple[int, int], options: RenderOptions) -> Image.Image | None:
    shadow_percent = max(0.0, min(0.2, options.shadow_percent))
    if shadow_percent <= 0:
        return None
    width, height = size
    pad = max(8, int(height * shadow_percent))
    layer = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    mask = Image.new("L", (width, height), 255)
    radius = int(min(size) * max(0.0, min(0.18, options.corner_radius_percent)))
    if radius > 0:
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=160)
    else:
        mask = ImageEnhance.Brightness(mask).enhance(0.55)
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 120))
    layer.alpha_composite(shadow, (pad, pad))
    layer.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(max(4, pad // 2))))
    return layer


def _parse_color(value: str, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    text = (value or "").strip()
    if not text:
        return fallback
    if text.startswith("#"):
        text = text[1:]
    try:
        if len(text) == 3:
            r, g, b = [int(char * 2, 16) for char in text]
        elif len(text) == 6:
            r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        else:
            return fallback
        return r, g, b, 255
    except ValueError:
        return fallback


def _position_for(canvas_size: tuple[int, int], item_size: tuple[int, int], position: WatermarkPosition, margin: int) -> tuple[int, int]:
    width, height = canvas_size
    item_w, item_h = item_size
    if position == WatermarkPosition.BOTTOM_LEFT:
        return margin, height - item_h - margin
    if position == WatermarkPosition.TOP_LEFT:
        return margin, margin
    if position == WatermarkPosition.TOP_RIGHT:
        return width - item_w - margin, margin
    if position == WatermarkPosition.CENTER:
        return (width - item_w) // 2, (height - item_h) // 2
    if position == WatermarkPosition.BOTTOM_CENTER:
        return (width - item_w) // 2, height - item_h - margin
    return width - item_w - margin, height - item_h - margin


def _load_font(size: int, italic: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = ITALIC_FONT_CANDIDATES + FONT_CANDIDATES if italic else FONT_CANDIDATES
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _load_title_font(size: int, font_name: str, italic: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if not font_name:
        return _load_font(size, italic=italic)
    for name, paths in TITLE_FONTS:
        if name == font_name:
            for path in paths:
                p = Path(path)
                if p.exists():
                    return ImageFont.truetype(str(p), size=size)
            break
    return _load_font(size, italic=italic)


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    if not text:
        return 0, 0
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int, font: ImageFont.ImageFont, fill: tuple[int, int, int, int]) -> None:
    width, _ = _text_size(draw, text, font)
    draw.text((center_x - width // 2, y), text, font=font, fill=fill)


def _draw_centered_tracking(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    tracking: int,
) -> None:
    widths = [_text_size(draw, char, font)[0] for char in text]
    total_width = sum(widths) + tracking * max(0, len(text) - 1)
    x = center_x - total_width // 2
    for char, char_width in zip(text, widths):
        draw.text((x, y), char, font=font, fill=fill)
        x += char_width + tracking


def _tracking_text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, tracking: int) -> tuple[int, int]:
    widths = [_text_size(draw, char, font)[0] for char in text]
    heights = [_text_size(draw, char, font)[1] for char in text]
    return sum(widths) + tracking * max(0, len(text) - 1), max(heights or [0])


def _draw_tracking(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    tracking: int,
) -> None:
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += _text_size(draw, char, font)[0] + tracking


def _draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    shadow: tuple[int, int, int, int],
) -> None:
    x, y = xy
    offset = max(1, int(font.size * 0.06)) if hasattr(font, "size") else 2
    draw.text((x + offset, y + offset), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)
