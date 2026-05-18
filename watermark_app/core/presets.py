from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from PySide6.QtCore import QSettings

from watermark_app.core.templates import BlurStyle, RenderOptions, TemplateKind, WatermarkPosition


@dataclass
class Preset:
    name: str
    template: TemplateKind
    is_system: bool = False
    title_position: WatermarkPosition | None = None
    title_offset_x_percent: float | None = None
    title_offset_y_percent: float | None = None
    title_opacity: float | None = None
    title_font_name: str | None = None
    text_scale: float | None = None
    exif_position: WatermarkPosition | None = None
    exif_scale: float | None = None
    exif_opacity: float | None = None
    exif_line_spacing: float | None = None
    exif_second_line_indent_percent: float | None = None
    exif_offset_x_percent: float | None = None
    exif_offset_y_percent: float | None = None
    logo_position: WatermarkPosition | None = None
    logo_scale: float | None = None
    logo_offset_x_percent: float | None = None
    logo_offset_y_percent: float | None = None
    opacity: float | None = None
    border_percent: float | None = None
    bottom_percent: float | None = None
    main_image_percent: float | None = None
    corner_radius_percent: float | None = None
    shadow_percent: float | None = None
    blur_percent: float | None = None
    blur_style: BlurStyle | None = None
    background_color: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "template": self.template.value, "is_system": self.is_system}
        for f in fields(self):
            if f.name in ("name", "template", "is_system"):
                continue
            value = getattr(self, f.name)
            if value is not None:
                if isinstance(value, (WatermarkPosition, BlurStyle)):
                    value = value.value
                data[f.name] = value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Preset:
        template = TemplateKind(data["template"])
        kwargs: dict[str, Any] = {"name": data["name"], "template": template, "is_system": data.get("is_system", False)}
        type_hints = {f.name: f.type for f in fields(cls)}
        for key, value in data.items():
            if key in ("name", "template", "is_system"):
                continue
            hint = type_hints.get(key, "")
            if "WatermarkPosition" in str(hint):
                kwargs[key] = WatermarkPosition(value)
            elif "BlurStyle" in str(hint):
                kwargs[key] = BlurStyle(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)

    def apply_to(self, options: RenderOptions) -> RenderOptions:
        data = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in ("name", "template", "is_system")}
        result = RenderOptions(**{f.name: getattr(options, f.name) for f in fields(options)})
        for key, value in data.items():
            if value is not None:
                setattr(result, key, value)
        return result

    @classmethod
    def from_render_options(cls, name: str, template: TemplateKind, options: RenderOptions, defaults: RenderOptions) -> Preset:
        kwargs: dict[str, Any] = {"name": name, "template": template}
        for f in fields(cls):
            if f.name in ("name", "template", "is_system"):
                continue
            current = getattr(options, f.name)
            default = getattr(defaults, f.name)
            if current != default:
                kwargs[f.name] = current
        return cls(**kwargs)


_SYSTEM_PRESETS: list[Preset] = [
    # --- Leica 风格白边 ---
    Preset(
        name="经典底部",
        template=TemplateKind.LEICA_FRAME,
        is_system=True,
    ),
    Preset(
        name="左下简约",
        template=TemplateKind.LEICA_FRAME,
        is_system=True,
        title_position=WatermarkPosition.BOTTOM_LEFT,
        exif_position=WatermarkPosition.BOTTOM_LEFT,
        logo_position=WatermarkPosition.BOTTOM_LEFT,
        border_percent=0.04,
        bottom_percent=0.14,
        text_scale=0.85,
    ),
    Preset(
        name="右下大字",
        template=TemplateKind.LEICA_FRAME,
        is_system=True,
        title_position=WatermarkPosition.BOTTOM_RIGHT,
        exif_position=WatermarkPosition.BOTTOM_RIGHT,
        logo_position=WatermarkPosition.BOTTOM_RIGHT,
        border_percent=0.06,
        bottom_percent=0.20,
        text_scale=1.30,
    ),
    # --- Hasselblad 底部水印 ---
    Preset(
        name="居中大字",
        template=TemplateKind.HASSELBLAD_FRAME,
        is_system=True,
    ),
    Preset(
        name="底部小字",
        template=TemplateKind.HASSELBLAD_FRAME,
        is_system=True,
        text_scale=0.80,
        opacity=0.70,
    ),
    Preset(
        name="左下角",
        template=TemplateKind.HASSELBLAD_FRAME,
        is_system=True,
        title_position=WatermarkPosition.BOTTOM_LEFT,
        exif_position=WatermarkPosition.BOTTOM_LEFT,
        logo_position=WatermarkPosition.BOTTOM_LEFT,
    ),
    # --- 模糊背景印框 ---
    Preset(
        name="标准模糊",
        template=TemplateKind.BLUR_FRAME,
        is_system=True,
    ),
    Preset(
        name="暗调电影",
        template=TemplateKind.BLUR_FRAME,
        is_system=True,
        blur_style=BlurStyle.DARK_CINEMA,
        main_image_percent=0.85,
        blur_percent=0.55,
    ),
    Preset(
        name="明亮奶油",
        template=TemplateKind.BLUR_FRAME,
        is_system=True,
        blur_style=BlurStyle.BRIGHT_CREAM,
        main_image_percent=0.92,
        blur_percent=0.40,
    ),
]


class PresetManager:
    def __init__(self, settings: QSettings):
        self._settings = settings
        self._system_presets: dict[TemplateKind, list[Preset]] = {}
        self._user_presets: dict[TemplateKind, list[Preset]] = {}
        self._init_system_presets()
        self._load_user_presets()

    def _init_system_presets(self) -> None:
        for preset in _SYSTEM_PRESETS:
            self._system_presets.setdefault(preset.template, []).append(preset)

    def _load_user_presets(self) -> None:
        self._settings.beginGroup("presets")
        for template_key in self._settings.childGroups():
            self._settings.beginGroup(template_key)
            try:
                template = TemplateKind(template_key)
            except ValueError:
                self._settings.endGroup()
                continue
            for name in self._settings.childGroups():
                self._settings.beginGroup(name)
                data: dict[str, Any] = {}
                for key in self._settings.childKeys():
                    data[key] = self._settings.value(key)
                self._settings.endGroup()
                if data:
                    data.setdefault("name", name)
                    data.setdefault("template", template_key)
                    data["is_system"] = False
                    try:
                        preset = Preset.from_dict(data)
                        self._user_presets.setdefault(template, []).append(preset)
                    except Exception:
                        pass
            self._settings.endGroup()
        self._settings.endGroup()

    def presets_for(self, template: TemplateKind) -> list[Preset]:
        result: list[Preset] = []
        result.extend(self._system_presets.get(template, []))
        result.extend(self._user_presets.get(template, []))
        return result

    def save_user_preset(self, preset: Preset) -> None:
        preset.is_system = False
        presets = self._user_presets.setdefault(preset.template, [])
        for i, existing in enumerate(presets):
            if existing.name == preset.name:
                presets[i] = preset
                break
        else:
            presets.append(preset)
        self._persist_user_preset(preset)

    def _persist_user_preset(self, preset: Preset) -> None:
        group = f"presets/{preset.template.value}/{preset.name}"
        self._settings.beginGroup(group)
        data = preset.to_dict()
        for key, value in data.items():
            if key not in ("name", "template", "is_system"):
                self._settings.setValue(key, value)
        self._settings.endGroup()

    def delete_user_preset(self, template: TemplateKind, name: str) -> bool:
        presets = self._user_presets.get(template, [])
        for i, preset in enumerate(presets):
            if preset.name == name:
                presets.pop(i)
                self._settings.remove(f"presets/{template.value}/{name}")
                return True
        return False

    def is_system_preset(self, template: TemplateKind, name: str) -> bool:
        for preset in self._system_presets.get(template, []):
            if preset.name == name:
                return True
        return False

    def default_preset(self, template: TemplateKind) -> Preset | None:
        presets = self.presets_for(template)
        return presets[0] if presets else None
