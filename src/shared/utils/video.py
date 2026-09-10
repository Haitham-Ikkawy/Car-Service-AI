"""Video upload validation for AI video diagnosis."""
from __future__ import annotations

from fastapi import UploadFile

from .translator import tr

MAX_VIDEO_BYTES = 20 * 1024 * 1024
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska", "video/3gpp"}
VIDEO_EXTS = ("mp4", "webm", "mov", "mkv", "3gp")


def validate_video(file: UploadFile, content: bytes, mime: str, lang: str) -> str | None:
    """Return a localized error message when the upload is invalid, else None."""
    if len(content) > MAX_VIDEO_BYTES:
        return tr(lang, "Video is larger than 20 MB.")
    ext = (file.filename or "").split(".")[-1].lower()
    if mime not in VIDEO_TYPES and ext not in VIDEO_EXTS:
        return tr(lang, "Please upload an MP4, WebM, MOV or MKV video.")
    if not content:
        return tr(lang, "Empty file.")
    return None
