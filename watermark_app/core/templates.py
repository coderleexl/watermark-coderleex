from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TemplateKind(str, Enum):
    NONE = "不使用相机参数"
    LEICA_FRAME = "Leica 风格白边"
    HASSELBLAD_FRAME = "Hasselblad 底部水印"
    BLUR_FRAME = "模糊背景印框"


class BlurStyle(str, Enum):
    GAUSSIAN = "高斯模糊"
    SOFT_FOCUS = "柔焦背景"
    VIGNETTE_GLASS = "暗角毛玻璃"
    CENTER_CLEAR = "中心清晰"
    GRADIENT_BLUR = "渐变模糊"
    RADIAL_ZOOM = "径向缩放"
    MOTION_BLUR = "轻微运动"
    MISTY_FILM = "降噪柔雾"
    DARK_CINEMA = "暗色电影"
    BRIGHT_CREAM = "亮色奶油"
    GRAIN_SOFT = "颗粒柔焦"


class WatermarkPosition(str, Enum):
    BOTTOM_LEFT = "左下"
    BOTTOM_RIGHT = "右下"
    TOP_LEFT = "左上"
    TOP_RIGHT = "右上"
    CENTER = "居中"
    BOTTOM_CENTER = "底部居中"


@dataclass
class RenderOptions:
    template: TemplateKind = TemplateKind.LEICA_FRAME
    position: WatermarkPosition = WatermarkPosition.BOTTOM_RIGHT
    title_text: str = "CODERLEEX"
    title_font_name: str = ""
    title_opacity: float = 1.0
    subtitle_text: str = ""
    enable_camera_info: bool = True
    enable_signature: bool = False
    signature_text: str = "CODERLEEX PHOTOGRAPHY"
    signature_position: WatermarkPosition = WatermarkPosition.BOTTOM_RIGHT
    signature_scale: float = 0.2
    signature_opacity: float = 0.38
    signature_offset_x_percent: float = 0.0
    signature_offset_y_percent: float = 0.0
    use_exif: bool = True
    show_title: bool = True
    title_position: WatermarkPosition = WatermarkPosition.BOTTOM_CENTER
    title_offset_x_percent: float = 0.0
    title_offset_y_percent: float = 0.0
    show_exif: bool = True
    exif_position: WatermarkPosition = WatermarkPosition.BOTTOM_LEFT
    exif_scale: float = 1.0
    exif_opacity: float = 0.85
    exif_line_spacing: float = 0.25
    exif_second_line_indent_percent: float = 0.0
    exif_offset_x_percent: float = 0.0
    exif_offset_y_percent: float = 0.0
    show_brand_logo: bool = True
    logo_position: WatermarkPosition = WatermarkPosition.BOTTOM_LEFT
    logo_scale: float = 0.14
    logo_offset_x_percent: float = 0.0
    logo_offset_y_percent: float = 0.0
    detail_template: str = "{camera} · {lens} · {focal} · {aperture} · {shutter} · {iso}"
    text_scale: float = 1.0
    opacity: float = 0.85
    border_percent: float = 0.055
    bottom_percent: float = 0.18
    main_image_percent: float = 0.9
    corner_radius_percent: float = 0.0
    shadow_percent: float = 0.0
    blur_percent: float = 0.45
    blur_style: BlurStyle = BlurStyle.GAUSSIAN
    background_color: str = "#f8f7f4"
    jpg_quality: int = 95
    png_watermark_path: str = ""
