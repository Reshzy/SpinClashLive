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

## Remaining keys (Prompt 2)

Simulation mode needs **no** Google keys. Live YouTube ingest uses backend-owned Google credentials only.

| Variable | Required? | What it is |
| --- | --- | --- |
| `GOOGLE_API_KEY` | Yes for a **public** live chat | YouTube Data API v3 key, restricted to that API (and ideally your IP) |
| `GOOGLE_OAUTH_CLIENT_ID` | Yes for **private/unlisted** chat | OAuth 2.0 Web client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes with the client ID | OAuth 2.0 client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | Default is fine locally | `http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback` |

- Public livestream with chat enabled: **API key only**.
- Private/unlisted acceptance test: **API key + OAuth client ID + client secret**, then a one-time browser consent. Scope is `https://www.googleapis.com/auth/youtube.readonly` only.
- Do **not** put Google passwords, refresh tokens, overlay tickets, or write-scope tokens in `.env`. OAuth refresh tokens are stored **encrypted at rest** in PostgreSQL (`google_credentials`) using `SECRET_KEY`.

Already handled by local defaults (not Google keys): `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `BOOTSTRAP_OWNER_USERNAME` / `BOOTSTRAP_OWNER_PASSWORD`.

Not a key, but required for the live check: YouTube Data API v3 enabled on the same project, a live video ID/URL with chat enabled, and `COLOR_RUSH_ENV=production`.

## Credentials placement

Copy `.env.example` to `.env` (never commit `.env`). Put real values **only** in `.env`. Keep `.env.example` as empty placeholders.

```text
GOOGLE_API_KEY=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback
YOUTUBE_TRANSPORT=stream
```

Never paste API keys or client secrets into chat, git, desktop config, or overlay bundles.

## Rotate and restrict an exposed API key

This environment has no `gcloud` CLI, so restriction/rotation must be done in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

1. Open **APIs & Services → Credentials**.
2. If a key was pasted into chat or committed, **delete it** (or disable it) and **Create credentials → API key**. Treat the old key as compromised.
3. Open the **new** key → **Edit** → **API restrictions** → Restrict key → **YouTube Data API v3**. Optionally set **Application restrictions** to your public IP.
4. Confirm **YouTube Data API v3** is enabled on that project.
5. Put the new key only in local `.env` as `GOOGLE_API_KEY`. Do not copy it into `.env.example`.

For private/unlisted chat, create **OAuth 2.0 Client ID** (Web application) on the same project. Authorized redirect URI: `http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback`. Put `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in `.env` only.

## Authorization

- Operator login (`POST /api/v1/auth/login`) is independent of Google.
- Console: **Authorize in browser** calls `POST /api/v1/admin/youtube/oauth/start` and opens the system browser. The backend callback is `GET /api/v1/admin/youtube/oauth/callback`. Status/revoke: `/api/v1/admin/youtube/oauth/status` and `/revoke`. Never paste Google passwords or refresh tokens into the UI.
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

If a live broadcast is not connected, live verification is **blocked**. Fixture tests under `backend/tests/application/test_youtube_contracts.py` check official JSON shapes only; they do not prove live API access.

## Generate gRPC stubs

```powershell
uv run python scripts/generate_youtube_stubs.py
```
