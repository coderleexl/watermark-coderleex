from __future__ import annotations

import re
from string import Formatter

from watermark_app.core.exif import PhotoMetadata


DEFAULT_DETAIL_TEMPLATE = "{camera} · {lens} · {focal} · {aperture} · {shutter} · {iso}"


def format_metadata_template(template: str, metadata: PhotoMetadata) -> str:
    values = metadata.template_values()
    chunks: list[str] = []
    for literal, field, format_spec, conversion in Formatter().parse(template or DEFAULT_DETAIL_TEMPLATE):
        chunks.append(literal)
        if field is None:
            continue
        value = values.get(field, "")
        if value and format_spec:
            value = format(value, format_spec)
        if conversion == "u":
            value = value.upper()
        elif conversion == "l":
            value = value.lower()
        chunks.append(value)
    return clean_template_text("".join(chunks))


def clean_template_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(\s*[·|/,-]\s*){2,}", " · ", text)
    text = re.sub(r"^[·|/,\-\s]+", "", text)
    text = re.sub(r"[·|/,\-\s]+$", "", text)
    return text.strip()
