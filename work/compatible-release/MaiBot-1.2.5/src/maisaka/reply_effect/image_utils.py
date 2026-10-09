"""回复效果记录中的图片/表情附件提取工具。"""

from base64 import b64encode
from pathlib import Path
from typing import Any

from src.common.data_models.message_component_data_model import EmojiComponent, ImageComponent, MessageSequence


_MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024


def extract_visual_attachments_from_sequence(message_sequence: MessageSequence | None) -> list[dict[str, Any]]:
    """从消息片段中提取可供评分页面展示的图片/表情信息。"""

    if message_sequence is None:
        return []

    attachments: list[dict[str, Any]] = []
    for index, component in enumerate(message_sequence.components):
        if isinstance(component, ImageComponent):
            attachments.append(_build_visual_attachment(component, index=index, kind="image"))
        elif isinstance(component, EmojiComponent):
            attachments.append(_build_visual_attachment(component, index=index, kind="emoji"))
    return attachments


def _build_visual_attachment(component: ImageComponent | EmojiComponent, *, index: int, kind: str) -> dict[str, Any]:
    binary_hash = str(component.binary_hash or "").strip()
    attachment: dict[str, Any] = {
        "kind": kind,
        "index": index,
        "hash": binary_hash,
        "content": str(component.content or "").strip(),
        "path": "",
        "data_url": "",
    }

    file_path = _resolve_image_path(binary_hash, kind=kind)
    if file_path:
        attachment["path"] = str(file_path)
        attachment["file_name"] = file_path.name
        attachment["mime_type"] = _guess_mime_type(file_path.suffix)
        return attachment

    binary_data = bytes(component.binary_data or b"")
    if binary_data and len(binary_data) <= _MAX_INLINE_IMAGE_BYTES:
        mime_type = _guess_mime_type_from_bytes(binary_data)
        attachment["mime_type"] = mime_type
        attachment["data_url"] = f"data:{mime_type};base64,{b64encode(binary_data).decode('ascii')}"
    return attachment


def _resolve_image_path(binary_hash: str, *, kind: str) -> Path | None:
    if not binary_hash:
        return None

    try:
        from sqlmodel import select

        from src.common.database.database import get_db_session
        from src.common.database.database_model import Images, ImageType

        image_type = ImageType.EMOJI if kind == "emoji" else ImageType.IMAGE
        with get_db_session() as db:
            statement = select(Images).filter_by(image_hash=binary_hash, image_type=image_type).limit(1)
            image_record = db.exec(statement).first()
        if image_record is None or getattr(image_record, "no_file_flag", False):
            return None
        file_path = Path(str(image_record.full_path or "")).expanduser().resolve()
        if file_path.is_file():
            return file_path
    except Exception:
        return None
    return None


def _guess_mime_type(suffix: str) -> str:
    normalized_suffix = suffix.lower().lstrip(".")
    if normalized_suffix in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized_suffix == "gif":
        return "image/gif"
    if normalized_suffix == "webp":
        return "image/webp"
    if normalized_suffix == "bmp":
        return "image/bmp"
    return "image/png"


def _guess_mime_type_from_bytes(binary_data: bytes) -> str:
    if binary_data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if binary_data.startswith(b"GIF8"):
        return "image/gif"
    if binary_data.startswith(b"RIFF") and b"WEBP" in binary_data[:16]:
        return "image/webp"
    if binary_data.startswith(b"BM"):
        return "image/bmp"
    return "image/png"
