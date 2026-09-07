"""Audio upload validation for AI sound diagnosis."""
from __future__ import annotations

from fastapi import UploadFile

from .translator import tr

MAX_AUDIO_BYTES = 15 * 1024 * 1024
AUDIO_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/x-m4a",
               "audio/mp4", "audio/ogg", "audio/webm", "audio/aac"}
AUDIO_EXTS = ("mp3", "wav", "m4a", "ogg", "webm", "aac")


def validate_audio(file: UploadFile, content: bytes, mime: str, lang: str) -> str | None:
    """Return a localized error message when the upload is invalid, else None."""
    if len(content) > MAX_AUDIO_BYTES:
        return tr(lang, "Audio is larger than 15 MB.")
    ext = (file.filename or "").split(".")[-1].lower()
    if mime not in AUDIO_TYPES and ext not in AUDIO_EXTS:
        return tr(lang, "Please upload an MP3, WAV, M4A, OGG or AAC file.")
    if not content:
        return tr(lang, "Empty file.")
    return None
