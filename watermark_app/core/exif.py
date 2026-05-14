from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image


EXIF_TAGS = {value: key for key, value in ExifTags.TAGS.items()}
GPS_TAGS = {value: key for key, value in ExifTags.GPSTAGS.items()}


@dataclass(frozen=True)
class PhotoMetadata:
    camera_make: str = ""
    camera_model: str = ""
    lens_model: str = ""
    focal_length: str = ""
    focal_length_35mm: str = ""
    aperture: str = ""
    shutter_speed: str = ""
    iso: str = ""
    date_taken: str = ""
    exposure_program: str = ""
    exposure_compensation: str = ""
    metering_mode: str = ""
    white_balance: str = ""

    @property
    def camera_label(self) -> str:
        make = self.camera_make.strip()
        model = self.camera_model.strip()
        if make and model.lower().startswith(make.lower()):
            return model
        parts = [make, model]
        return " ".join(part for part in parts if part)

    @property
    def exposure_label(self) -> str:
        parts = [self.focal_length, self.aperture, self.shutter_speed, self.iso]
        return " · ".join(part for part in parts if part)

    @property
    def detail_label(self) -> str:
        parts = [self.camera_label, self.lens_model, self.exposure_label]
        return " · ".join(part for part in parts if part)

    @property
    def brand_label(self) -> str:
        return normalize_brand(self.camera_make or self.camera_model)

    def template_values(self) -> dict[str, str]:
        return {
            "brand": self.brand_label,
            "make": self.camera_make,
            "model": self.camera_model,
            "camera": self.camera_label,
            "lens": self.lens_model,
            "focal": self.focal_length,
            "focal35": self.focal_length_35mm,
            "aperture": self.aperture,
            "shutter": self.shutter_speed,
            "iso": self.iso,
            "date": self.date_taken,
            "mode": self.exposure_program,
            "ev": self.exposure_compensation,
            "metering": self.metering_mode,
            "wb": self.white_balance,
        }


def read_photo_metadata(path: str | Path) -> PhotoMetadata:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return PhotoMetadata()

            data = _collect_exif_data(exif)
            return PhotoMetadata(
                camera_make=_clean_text(data.get("Make")),
                camera_model=_clean_text(data.get("Model")),
                lens_model=_clean_text(data.get("LensModel") or data.get("LensSpecification")),
                focal_length=_format_focal_length(data.get("FocalLength")),
                focal_length_35mm=_format_focal_length(data.get("FocalLengthIn35mmFilm") or data.get("FocalLengthIn35mmFormat")),
                aperture=_format_aperture(data.get("FNumber")),
                shutter_speed=_format_shutter(data.get("ExposureTime")),
                iso=_format_iso(data.get("ISOSpeedRatings") or data.get("PhotographicSensitivity")),
                date_taken=_format_date(data.get("DateTimeOriginal") or data.get("DateTime")),
                exposure_program=_format_exposure_program(data.get("ExposureProgram")),
                exposure_compensation=_format_exposure_compensation(data.get("ExposureBiasValue")),
                metering_mode=_format_metering_mode(data.get("MeteringMode")),
                white_balance=_format_white_balance(data.get("WhiteBalance")),
            )
    except Exception:
        return PhotoMetadata()


def _collect_exif_data(exif: Image.Exif) -> dict[str, Any]:
    data = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif.items()}
    for ifd in [ExifTags.IFD.Exif, ExifTags.IFD.GPSInfo]:
        try:
            nested = exif.get_ifd(ifd)
        except Exception:
            nested = {}
        for tag, value in nested.items():
            if ifd == ExifTags.IFD.GPSInfo:
                name = ExifTags.GPSTAGS.get(tag, tag)
            else:
                name = ExifTags.TAGS.get(tag, tag)
            data[name] = value
    return data


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, tuple):
        return " ".join(_clean_text(item) for item in value if item)
    return str(value).replace("\x00", "").strip()


def _fraction_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, Fraction):
            return float(value)
        if isinstance(value, tuple) and len(value) == 2:
            numerator, denominator = value
            return float(numerator) / float(denominator)
        return float(value)
    except Exception:
        return None


def _format_focal_length(value: Any) -> str:
    focal = _fraction_float(value)
    if focal is None:
        return ""
    if focal.is_integer():
        return f"{int(focal)}mm"
    return f"{focal:.1f}mm"


def _format_aperture(value: Any) -> str:
    aperture = _fraction_float(value)
    if aperture is None:
        return ""
    return f"f/{aperture:.1f}".replace(".0", "")


def _format_shutter(value: Any) -> str:
    seconds = _fraction_float(value)
    if seconds is None or seconds <= 0:
        return ""
    if seconds >= 1:
        return f"{seconds:.1f}s".replace(".0", "")
    denominator = round(1 / seconds)
    return f"1/{denominator}s"


def _format_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    try:
        return f"ISO {int(value)}"
    except Exception:
        return ""


def _format_date(value: Any) -> str:
    text = _clean_text(value)
    if len(text) >= 10 and text[4] == ":" and text[7] == ":":
        return text[:10].replace(":", "-")
    return text


def _format_exposure_program(value: Any) -> str:
    mapping = {
        0: "",
        1: "M",
        2: "P",
        3: "A",
        4: "S",
        5: "Creative",
        6: "Action",
        7: "Portrait",
        8: "Landscape",
    }
    try:
        return mapping.get(int(value), "")
    except Exception:
        return _clean_text(value)


def _format_exposure_compensation(value: Any) -> str:
    compensation = _fraction_float(value)
    if compensation is None:
        return ""
    sign = "+" if compensation > 0 else ""
    return f"{sign}{compensation:.1f}EV".replace(".0EV", "EV")


def _format_metering_mode(value: Any) -> str:
    mapping = {
        1: "Average",
        2: "Center",
        3: "Spot",
        4: "Multi-spot",
        5: "Multi",
        6: "Partial",
        255: "Other",
    }
    try:
        return mapping.get(int(value), "")
    except Exception:
        return _clean_text(value)


def _format_white_balance(value: Any) -> str:
    mapping = {
        0: "Auto WB",
        1: "Manual WB",
    }
    try:
        return mapping.get(int(value), "")
    except Exception:
        return _clean_text(value)


def normalize_brand(value: str) -> str:
    text = value.upper().replace("CORPORATION", "").replace("CORP.", "").strip()
    aliases = {
        "SONY": "SONY",
        "NIKON": "NIKON",
        "CANON": "CANON",
        "FUJIFILM": "FUJIFILM",
        "FUJI": "FUJIFILM",
        "LEICA": "LEICA",
        "HASSELBLAD": "HASSELBLAD",
        "PANASONIC": "PANASONIC",
        "OLYMPUS": "OLYMPUS",
        "OM DIGITAL": "OLYMPUS",
        "RICOH": "RICOH",
        "PENTAX": "PENTAX",
        "SIGMA": "SIGMA",
        "DJI": "DJI",
    }
    for key, label in aliases.items():
        if key in text:
            return label
    return text.split()[0] if text else ""
