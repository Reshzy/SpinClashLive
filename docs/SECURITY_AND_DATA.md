# Security and data — Color Rush Live

## API data versus game data

YouTube API data includes channel IDs, display names, avatar URLs, live chat message IDs, published timestamps, continuation tokens, and OAuth/API credentials. The backend retains the **minimum** needed to identify a player and classify a command.

Application-generated game data includes internal player UUIDs, picks, score ledger rows, period aggregates, archives, champions, round state, presentation plans, and operator audit records. Game points are game points, not YouTube audience or performance metrics.

Separating application scores from API data does **not** automatically grant permission to retain linked YouTube identifiers forever.

## Retention (defaults)

| Data | Default |
| --- | --- |
| Raw/normalized command inbox | 7 days, then purge job |
| Profile/avatar cache | refresh in bounded batches; follow current YouTube 30-day limits where applicable |
| Scores, streaks, archives | retained as game records until a data-deletion request |
| Google tokens | until disconnect/revocation |
| Overlay tickets | TTL plus explicit revoke |
| Backups | expiry is a restore/ops policy; deletion is not instant from old backups |

## Deletion

`POST /api/v1/admin/players/{player_id}/delete-data` (OWNER):

- Anonymizes display name and channel id in SQL
- Sets `deleted_at` / `anonymized_at`
- Removes Redis leaderboard members for that player
- Writes an audit row

Old backups may still contain identifiers until those backups expire. Do not claim instant worldwide erasure.

## Production API-use review (outstanding)

Long-term identity and leaderboard retention, and the proposed game use case, need an **explicit review against current YouTube API Terms and Developer Policies** before production. Record the outcome of that review here when it happens. This file is the placeholder for that review; it is **not** complete.

Do not reward watch time, subscriptions, paid messages, or donations. Super Chat and membership events are ignored for scoring.

## Credentials and transport

- Operator JWT access + hashed refresh sessions
- Overlay tickets are read-only and cannot call admin routes
- Loopback bind by default; CORS/WebSocket origins are configured
- Metrics restricted to trusted/loopback when `TRUSTED_METRICS` is disabled
- Google YouTube secrets (`GOOGLE_API_KEY`, OAuth client id/secret) live only in gitignored `.env`; never in `.env.example`, desktop config, overlay bundles, or chat
- An API key pasted into chat or committed to git is compromised: rotate it in Cloud Console and restrict the replacement to YouTube Data API v3 (`docs/YOUTUBE_SETUP.md`)
- No secrets in overlay assets or TypeScript bundles
- Structured logs must not include tokens, full chat bodies, or profile secrets
