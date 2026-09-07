"""Image upload validation for AI image diagnosis."""
from __future__ import annotations

from fastapi import UploadFile

from .translator import tr

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp")


def validate_image(file: UploadFile, content: bytes, mime: str, lang: str) -> str | None:
    """Return a localized error message when the upload is invalid, else None."""
    if len(content) > MAX_IMAGE_BYTES:
        return tr(lang, "Image is larger than 10 MB.")
    ext = (file.filename or "").split(".")[-1].lower()
    if mime not in IMAGE_TYPES and ext not in IMAGE_EXTS:
        return tr(lang, "Please upload a JPG, PNG or WebP image.")
    if not content:
        return tr(lang, "Empty file.")
    return None
