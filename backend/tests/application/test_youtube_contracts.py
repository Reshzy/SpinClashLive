import pytest

from color_rush.domain.enums import SourceHealth
from color_rush.domain.errors import InvalidCommandError
from color_rush.infrastructure.youtube.normalize import classify_youtube_error, normalize_live_chat_items
from color_rush.infrastructure.youtube.video import parse_video_ref


def test_parse_video_id_and_urls() -> None:
    assert parse_video_ref("abcdefghijk") == "abcdefghijk"
    assert parse_video_ref("https://youtu.be/abcdefghijk") == "abcdefghijk"
    assert parse_video_ref("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert parse_video_ref("https://www.youtube.com/live/abcdefghijk") == "abcdefghijk"
    with pytest.raises(InvalidCommandError):
        parse_video_ref("https://example.com/watch?v=abcdefghijk")


def test_normalize_official_list_shape() -> None:
    payload = {
        "kind": "youtube#liveChatMessageListResponse",
        "nextPageToken": "token-2",
        "pollingIntervalMillis": 4000,
        "items": [
            {
                "id": "msg-1",
                "snippet": {
                    "type": "textMessageEvent",
                    "publishedAt": "2026-10-04T08:00:00Z",
                    "displayMessage": "!red",
                    "textMessageDetails": {"messageText": "!red"},
                },
                "authorDetails": {
                    "channelId": "UC123",
                    "displayName": "Ada",
                    "profileImageUrl": "https://i.ytimg.com/x.jpg",
                },
            },
            {
                "id": "super-1",
                "snippet": {"type": "superChatEvent", "publishedAt": "2026-10-04T08:00:01Z"},
                "authorDetails": {"channelId": "UC999", "displayName": "Paid"},
            },
        ],
    }
    commands = normalize_live_chat_items(payload["items"], broadcast_id="vid")
    assert len(commands) == 1
    assert commands[0].command_text == "!red"
    assert commands[0].provider_channel_id == "UC123"


def test_error_classification() -> None:
    assert classify_youtube_error(403, "liveChatEnded") is SourceHealth.ENDED
    assert classify_youtube_error(401, None) is SourceHealth.RESYNC
    assert classify_youtube_error(429, "rateLimitExceeded") is SourceHealth.QUOTA
    assert classify_youtube_error(None, None, grpc_code=7) is SourceHealth.PERMISSION
