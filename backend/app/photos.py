from __future__ import annotations

import asyncio
import logging
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps

from .config import settings

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_BYTES = 5 * 1024 * 1024
MAX_EDGE = 960
JPEG_QUALITY = 82
# Already-small files are left alone so startup does not re-encode them.
OPTIMIZE_BYTES = 180_000
MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"RIFF", ".webp"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def cocktail_photo_url(filename: str | None) -> str | None:
    if not filename:
        return None
    return f"/media/{filename}"


def _extension_for(content: bytes, content_type: str | None) -> str:
    if content_type in ALLOWED_TYPES:
        if content_type == "image/webp" and not content.startswith(b"RIFF"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo does not look like a valid image")
        return ALLOWED_TYPES[content_type]
    for prefix, ext in MAGIC:
        if content.startswith(prefix):
            if ext == ".webp" and b"WEBP" not in content[:16]:
                continue
            return ext
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo must be JPEG, PNG, WebP, or GIF")


def _flatten(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 252, 246))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return img.convert("RGB")


def compress_image(content: bytes) -> bytes:
    try:
        with Image.open(BytesIO(content)) as opened:
            img = ImageOps.exif_transpose(opened)
            img = _flatten(img)
            img.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, format="JPEG", quality=JPEG_QUALITY, progressive=True)
            return out.getvalue()
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo could not be read") from exc


def _needs_optimize(path: Path) -> bool:
    if path.stat().st_size > OPTIMIZE_BYTES:
        return True
    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception:
        return False
    return max(width, height) > MAX_EDGE


def optimize_stored_photos() -> None:
    """Shrink photos saved before upload compression, once. Filenames are content-addressed, so a rewrite gets a new URL."""
    from .database import SessionLocal
    from .models import Cocktail

    db = SessionLocal()
    try:
        rows = db.query(Cocktail).filter(Cocktail.photo_filename.is_not(None)).all()
        for row in rows:
            name = Path(row.photo_filename or "").name
            if not name or name != row.photo_filename:
                continue
            path = settings.upload_dir / name
            if not path.is_file() or not _needs_optimize(path):
                continue
            raw = path.read_bytes()
            try:
                optimized = compress_image(raw)
            except HTTPException:
                logger.warning("Leaving unreadable cocktail photo %s in place", name)
                continue
            if len(optimized) >= len(raw):
                continue
            new_name = f"{uuid.uuid4().hex}.jpg"
            (settings.upload_dir / new_name).write_bytes(optimized)
            row.photo_filename = new_name
            db.commit()
            _unlink_quiet(path)
            logger.info("Shrunk cocktail photo %s from %d to %d bytes", name, len(raw), len(optimized))
        _delete_orphan_uploads(db)
    finally:
        db.close()


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.info("Could not remove old photo %s yet; it is still open", path.name)


def _delete_orphan_uploads(db) -> None:
    from .models import Cocktail

    keep = {
        filename
        for (filename,) in db.query(Cocktail.photo_filename).filter(Cocktail.photo_filename.is_not(None)).all()
    }
    for path in settings.upload_dir.iterdir():
        if path.name == ".gitkeep" or not path.is_file() or path.name in keep:
            continue
        _unlink_quiet(path)


async def save_photo(upload: UploadFile) -> str:
    content = await upload.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty photo")
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo is larger than 5 MB")
    _extension_for(content, upload.content_type)
    optimized = await asyncio.to_thread(compress_image, content)
    filename = f"{uuid.uuid4().hex}.jpg"
    dest = settings.upload_dir / filename
    await asyncio.to_thread(dest.write_bytes, optimized)
    return filename


def delete_photo(filename: str | None) -> None:
    if not filename:
        return
    path = settings.upload_dir / Path(filename).name
    if path.exists() and path.is_file():
        path.unlink()
