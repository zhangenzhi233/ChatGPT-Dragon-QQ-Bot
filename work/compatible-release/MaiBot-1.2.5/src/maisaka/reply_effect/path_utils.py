"""回复效果日志路径工具。"""

from pathlib import Path

from src.maisaka.display.preview_path_utils import build_preview_chat_dir_name, normalize_preview_name

BASE_DIR = Path("logs") / "maisaka_reply_effect"


def build_reply_effect_chat_dir_name(session_id: str) -> str:
    """构建回复效果日志的会话目录名。"""

    chat_dir_name = build_preview_chat_dir_name(session_id)
    normalized_chat_dir_name = normalize_preview_name(chat_dir_name)
    if normalized_chat_dir_name != "unknown":
        return normalized_chat_dir_name
    return "unknown_chat"


def build_reply_effect_chat_dir(session_id: str, base_dir: Path | None = None) -> Path:
    """返回某个会话对应的回复效果日志目录。"""

    root_dir = base_dir or BASE_DIR
    return root_dir / build_reply_effect_chat_dir_name(session_id)
