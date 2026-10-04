# YouTube Live chat setup — Color Rush Live

These steps configure the **backend-owned** YouTube Data API v3 / Live Streaming API connection. Operator console login is a separate credential. Rechecked against Google docs on 2026-10-04 (`liveChatMessages.streamList`, `liveChatMessages.list`, streaming-live-chat guide).

This document does **not** claim YouTube approval, monetization eligibility, or unrestricted chat delivery.

## Google Cloud project

1. Create or select a Google Cloud project.
2. Enable **YouTube Data API v3**.
3. Configure an OAuth consent screen (External or Internal). App name can be Color Rush Live.
4. Create credentials:
   - **API key** for supported public live-chat reads. Restrict it to YouTube Data API v3 and expected IPs.
   - **OAuth 2.0 Client ID** (Web application) if the chat is not readable with an API key. Authorized redirect: `http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback` for local development.
5. Do not request write scopes. Color Rush Live uses `https://www.googleapis.com/auth/youtube.readonly` only.

## Credentials placement

Copy `.env.example` to `.env` (never commit `.env`):

```text
GOOGLE_API_KEY=...
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback
YOUTUBE_TRANSPORT=stream
```

OAuth refresh tokens are stored **encrypted at rest** in PostgreSQL (`google_credentials`) using `SECRET_KEY`. They never belong in desktop config examples or overlay bundles.

## Authorization

- Operator login (`POST /api/v1/auth/login`) is independent of Google.
- `POST /api/v1/admin/youtube/connect` accepts a video ID or supported URL (`watch?v=`, `youtu.be`, `/live/`), resolves `liveStreamingDetails.activeLiveChatId` via `videos.list`, and starts one owned reader.
- Streaming transport: gRPC `V3DataLiveChatMessageService.StreamList` at `dns:///youtube.googleapis.com:443` using vendored `backend/third_party/youtube/stream_list.proto`.
- Fallback: HTTP `GET https://www.googleapis.com/youtube/v3/liveChat/messages` respecting `pollingIntervalMillis`.
- Invalid/expired continuation tokens surface as `resync`. The backend does not claim missed chat was recovered.

## Broadcast prerequisites

- Chat must be enabled.
- For a private/unlisted acceptance test, use an account that can read that chat.
- One backend ingest owner per live chat. Extra workers must not open extra YouTube readers.

## Disconnect and revocation

- `POST /api/v1/admin/youtube/disconnect` clears the session live-chat binding.
- Revoke Google credentials in Cloud Console and mark rows revoked in `google_credentials`.
- Overlay tickets are unrelated and can be revoked at `/api/v1/admin/overlay-tickets/{id}/revoke`.

## Private-stream acceptance

Requires live credentials. Do not mark this passed without running it.

```powershell
$env:GOOGLE_API_KEY = "<restricted-key>"
$env:COLOR_RUSH_ENV = "production"
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
# login as owner, POST /api/v1/admin/youtube/connect with the private video id
# confirm source health is healthy, send !red in chat, confirm an inbox row
```

If credentials are unavailable, live verification is **blocked**. Fixture tests under `backend/tests/application/test_youtube_contracts.py` check official JSON shapes only; they do not prove live API access.

## Generate gRPC stubs

```powershell
uv run python scripts/generate_youtube_stubs.py
```
