"""Smaller WebP copies of uploaded images for the storefront.

Uploads are kept as sent (up to 8 MB, up to 8192 px); phones downloaded those
originals for every product card. A copy at a fixed width is made on the first
request and kept next to the media in ``.variants`` (nginx never serves dot
directories), so photos uploaded before this release get copies too, with no
migration. Animated images are served as uploaded.
"""
from __future__ import annotations

import os
import re
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# Widths offered to the browser in srcset: phone card, phone detail / desktop
# card, desktop detail, retina detail.
WIDTHS = (320, 640, 960, 1600)
NAME = re.compile(r"^[A-Za-z0-9_-]+\.(?:png|jpe?g|webp|gif)$")
QUALITY = 80
MAX_PIXELS = 20_000_000


def _directory() -> Path:
    from shop.paths import media_dir
    return media_dir()


def variants_dir() -> Path:
    path = _directory() / ".variants"
    path.mkdir(exist_ok=True)
    return path


def _target(name: str, width: int) -> Path:
    stem, extension = name.rsplit(".", 1)
    return variants_dir() / f"{stem}-{extension}-w{width}.webp"


def _encode(source: Path, width: int) -> bytes | None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source, formats=["JPEG", "PNG", "GIF", "WEBP"]) as image:
            if image.width * image.height > MAX_PIXELS:
                return None
            if getattr(image, "n_frames", 1) > 1:
                return None  # animation: keep the original
            frame = ImageOps.exif_transpose(image)
            frame = frame.convert("RGBA" if frame.mode in ("RGBA", "LA", "P", "PA") else "RGB")
            frame.thumbnail((width, width * 4), Image.Resampling.LANCZOS)
            output = BytesIO()
            frame.save(output, format="WEBP", quality=QUALITY, method=4)
            return output.getvalue()


def variant(name: str, width: int) -> Path | None:
    """Path to the WebP copy of a media file at this width, or None to serve the original."""
    if width not in WIDTHS or not NAME.fullmatch(name or ""):
        return None
    source = _directory() / name
    if not source.is_file() or source.is_symlink():
        return None
    target = _target(name, width)
    try:
        if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
            return target
        content = _encode(source, width)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None
    if content is None:
        return None
    if content and len(content) >= source.stat().st_size and source.suffix.lower() == ".webp":
        return None  # the original is already smaller
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, target)
    return target


def forget(name: str) -> None:
    """Delete the copies of a media file that was removed."""
    if not NAME.fullmatch(name or ""):
        return
    stem, extension = name.rsplit(".", 1)
    directory = _directory() / ".variants"
    if directory.is_dir():
        for path in directory.glob(f"{stem}-{extension}-w*.webp"):
            path.unlink(missing_ok=True)
