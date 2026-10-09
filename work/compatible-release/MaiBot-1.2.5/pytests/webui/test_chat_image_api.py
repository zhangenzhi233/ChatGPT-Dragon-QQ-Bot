from base64 import b64encode

import asyncio

import pytest

from src.webui.routers.chat.service import create_message_data, normalize_chat_images
from src.webui.routers.websocket import unified as unified_ws


PNG_BASE64 = b64encode(b"\x89PNG\r\n\x1a\nimage-bytes").decode("ascii")


def test_normalize_chat_images_accepts_base64_and_data_url() -> None:
    images = normalize_chat_images(
        [
            {
                "name": "base64.png",
                "mime_type": "image/png",
                "base64": PNG_BASE64,
            },
            {
                "name": "data-url.webp",
                "mimeType": "image/webp",
                "dataUrl": f"data:image/webp;base64,{PNG_BASE64}",
            },
        ]
    )

    assert images == [
        {
            "name": "base64.png",
            "mime_type": "image/png",
            "base64": PNG_BASE64,
        },
        {
            "name": "data-url.webp",
            "mime_type": "image/webp",
            "base64": PNG_BASE64,
        },
    ]


def test_normalize_chat_images_rejects_invalid_payloads_and_limits_count() -> None:
    raw_images = [
        {"name": "not-image.txt", "mime_type": "text/plain", "base64": PNG_BASE64},
        {"name": "broken.png", "mime_type": "image/png", "base64": "not-base64"},
    ]
    raw_images.extend(
        {
            "name": f"{index}.png",
            "mime_type": "image/png",
            "base64": PNG_BASE64,
        }
        for index in range(10)
    )

    images = normalize_chat_images(raw_images)

    assert len(images) == 6
    assert all(image["base64"] == PNG_BASE64 for image in images)


def test_create_message_data_preserves_text_and_image_segments() -> None:
    message_data = create_message_data(
        content="看看这张图",
        user_id="webui_user_alice",
        user_name="Alice",
        images=[
            {
                "name": "cat.png",
                "mime_type": "image/png",
                "base64": PNG_BASE64,
            }
        ],
    )

    assert message_data["processed_plain_text"] == "看看这张图\n[图片]"
    assert message_data["message_segment"] == {
        "type": "seglist",
        "data": [
            {
                "type": "text",
                "data": "看看这张图",
            },
            {
                "type": "image",
                "data": PNG_BASE64,
            },
        ],
    }


@pytest.mark.asyncio
async def test_chat_websocket_send_accepts_image_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: list[dict[str, object]] = []
    processed_payloads: list[dict[str, object]] = []

    class FakeWebSocketManager:
        def get_chat_session_id(self, connection_id: str, client_session_id: str) -> str:
            assert connection_id == "connection-1"
            assert client_session_id == "tab-1"
            return "internal-session-1"

        async def send_response(
            self,
            connection_id: str,
            request_id: str | None,
            ok: bool,
            data: dict[str, object] | None = None,
            error: dict[str, object] | None = None,
        ) -> None:
            responses.append(
                {
                    "connection_id": connection_id,
                    "request_id": request_id,
                    "ok": ok,
                    "data": data or {},
                    "error": error or {},
                }
            )

    async def fake_process_chat_message(
        connection_id: str,
        client_session_id: str,
        data: dict[str, object],
    ) -> None:
        processed_payloads.append(
            {
                "connection_id": connection_id,
                "client_session_id": client_session_id,
                **data,
            }
        )

    monkeypatch.setattr(unified_ws, "websocket_manager", FakeWebSocketManager())
    monkeypatch.setattr(unified_ws, "_process_chat_message", fake_process_chat_message)

    await unified_ws._handle_chat_message_send(
        "connection-1",
        {
            "id": "request-1",
            "session": "tab-1",
            "data": {
                "content": "带图消息",
                "images": [
                    {
                        "name": "cat.png",
                        "mime_type": "image/png",
                        "base64": PNG_BASE64,
                    }
                ],
                "user_name": "Alice",
            },
        },
    )
    await asyncio.sleep(0)

    assert responses == [
        {
            "connection_id": "connection-1",
            "request_id": "request-1",
            "ok": True,
            "data": {"accepted": True, "session": "tab-1"},
            "error": {},
        }
    ]
    assert processed_payloads == [
        {
            "connection_id": "connection-1",
            "client_session_id": "tab-1",
            "type": "message",
            "content": "带图消息",
            "images": [
                {
                    "name": "cat.png",
                    "mime_type": "image/png",
                    "base64": PNG_BASE64,
                }
            ],
            "emojis": [],
            "files": [],
            "voices": [],
            "user_name": "Alice",
        }
    ]
